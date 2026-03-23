'use strict';

let mediaRecorder;
let audioChunks = [];
let stream;
let isRecording = false;
let currentChunkStartTime = null;
let currentChunkEndTime = null;
let screenRecorder, screenChunks = [];
let lastChatResult = null;
let vadEnabled = false;
let vadController = null;
let vadMicStream = null;
let shouldUploadScreenRecording = false;
let timerInterval = null;
let timeRemaining = 900;
const UPLOAD_MAX_RETRIES = 3;
const UPLOAD_RETRY_DELAY_MS = 2000;
window.timeRemaining = timeRemaining;
window.skipNextSilenceEntry = false;
const transcription = document.getElementById('transcription');
const ttsAudio = document.getElementById('ttsAudio');
const backendBaseUrl = backendUrl();

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function setUploadStatus(status) {
    const messageByStatus = {
        uploading: 'Resultaten uploaden...',
        success: 'Upload succesvol!',
        error: 'Upload mislukt. Probeer later opnieuw.'
    };
    const message = messageByStatus[status] || status;

    if (window.timerButton) {
        if (status === 'uploading') {
            window.timerButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Resultaten uploaden...';
        } else {
            window.timerButton.textContent = message;
        }
    }

    if (window.recordButton) {
        window.recordButton.disabled = status === 'uploading';
        if (status === 'success') {
            const canContinue = window.timeRemaining > 0;
            window.recordButton.style.display = canContinue ? '' : 'none';
            if (canContinue) {
                window.recordButton.disabled = false;
                window.recordButton.textContent = 'Toch verderdoen?';
                window.recordButton.dataset.sessionState = 'resume';
            }
        }
        if (status === 'error') {
            window.recordButton.style.display = '';
            window.recordButton.disabled = false;
            window.recordButton.textContent = 'Start onderzoek';
            window.recordButton.dataset.sessionState = 'start';
        }
    }
}

function startTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        timeRemaining--;
        window.timeRemaining = timeRemaining;
        const minutes = Math.floor(timeRemaining / 60);
        const seconds = timeRemaining % 60;
        const timerLabel = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        if (window.recordButton) {
            window.recordButton.textContent = 'Onderzoek vroegtijdig stoppen';
            window.recordButton.dataset.sessionState = 'active';
        }
        if (window.timerButton) {
            window.timerButton.textContent = timerLabel;
        }
        if (timeRemaining <= 0) {
            stopTimer();
            disableVoiceActivation(true);
        }
    }, 1000);
}

function stopTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = null;
}

async function uploadScreenRecording(blob) {
    const participantId = localStorage.getItem('participant_id');
    const fileName = `screen-recording-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`;
    let lastError = null;

    for (let attempt = 1; attempt <= UPLOAD_MAX_RETRIES; attempt++) {
        const formData = new FormData();
        formData.append('video', blob, fileName);
        formData.append('participant_id', participantId);

        try {
            const response = await fetch(`${backendBaseUrl}/upload-video`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Upload failed with status ${response.status}`);
            }

            return;
        } catch (error) {
            lastError = error;
            if (attempt < UPLOAD_MAX_RETRIES) {
                await delay(UPLOAD_RETRY_DELAY_MS);
            }
        }
    }

    throw lastError;
}

function startScreenRecording(sessionAudioStream) {
    if (!window.videoStream || (screenRecorder && screenRecorder.state !== 'inactive')) {
        return;
    }

    const screenStream = new MediaStream([
        ...window.videoStream.getVideoTracks(),
        ...sessionAudioStream.getAudioTracks()
    ]);

    screenRecorder = new MediaRecorder(screenStream);
    screenChunks = [];
    shouldUploadScreenRecording = false;

    screenRecorder.ondataavailable = event => {
        if (event.data.size > 0) {
            screenChunks.push(event.data);
        }
    };

    screenRecorder.onstop = async () => {
        if (!shouldUploadScreenRecording || screenChunks.length === 0) {
            screenChunks = [];
            shouldUploadScreenRecording = false;
            return;
        }

        const blob = new Blob(screenChunks, { type: 'video/webm' });
        screenChunks = [];

        try {
            setUploadStatus('uploading');
            await uploadScreenRecording(blob);
            console.log('Video uploaded successfully');
            setUploadStatus('success');
        } catch (error) {
            console.error('Error uploading video:', error);
            setUploadStatus('error');
        } finally {
            shouldUploadScreenRecording = false;
        }
    };

    screenRecorder.start();
}

async function startRecording(sharedStream) {
    isRecording = true;
    currentChunkStartTime = new Date().toISOString();
    currentChunkEndTime = null;
    stream = sharedStream || await navigator.mediaDevices.getUserMedia({ audio: true });

    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
    mediaRecorder.onstop = async () => {
        const shouldSkipSilenceEntry = Boolean(window.skipNextSilenceEntry);
        window.skipNextSilenceEntry = false;

        if (!sharedStream) {
            stream.getTracks().forEach(track => track.stop());
        }
        isRecording = false;

        try {
            const formData = new FormData();
            formData.append('audio', new Blob(audioChunks));
            const response = await fetch(`${backendBaseUrl}/transcribe`, {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            transcription.textContent = "Prompt: " + result.transcription;

            if (result.transcription) {
                const formDataChat = new FormData();
                formDataChat.append('transcript', result.transcription);
                if (window.screenshotBase64) {
                    formDataChat.append('screenshot', window.screenshotBase64);
                }
                if (lastChatResult && lastChatResult.response_id) {
                    formDataChat.append('previous_response_id', lastChatResult.response_id);
                }
                const participantId = localStorage.getItem('participant_id');
                if (participantId) {
                    formDataChat.append('participant_id', participantId);
                }
                if (shouldSkipSilenceEntry) {
                    formDataChat.append('skip_silence_entry', 'true');
                }
                formDataChat.append('start_time', currentChunkStartTime || new Date().toISOString());
                formDataChat.append('end_time', currentChunkEndTime || new Date().toISOString());
                const chatResponse = await fetch(`${backendBaseUrl}/chat`, {
                    method: 'POST',
                    body: formDataChat
                });
                const chatResult = await chatResponse.json();
                lastChatResult = chatResult;
                transcription.textContent += '\nChat model response: ' + chatResult.response;

                // if (chatResult.response) {
                //     const formDataTTS = new FormData();
                //     formDataTTS.append('text', chatResult.response);
                //     const ttsResponse = await fetch(`${backendBaseUrl}/tts-stream`, {
                //         method: 'POST',
                //         body: formDataTTS
                //     });
                //     const ttsBlob = await ttsResponse.blob();
                //     const ttsObjectUrl = URL.createObjectURL(ttsBlob);
                //     ttsAudio.src = ttsObjectUrl;
                //     ttsAudio.play();
                // }
            }
        } catch (error) {
            transcription.textContent = 'Error: Server reageert niet.';
        }
    };
    mediaRecorder.start();
}

function stopAudioChunkRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        if (!currentChunkEndTime) {
            currentChunkEndTime = new Date().toISOString();
        }
        mediaRecorder.stop();
    }
}

function stopSessionScreenRecording(uploadToDrive = false) {
    if (screenRecorder && screenRecorder.state !== 'inactive') {
        shouldUploadScreenRecording = uploadToDrive;
        screenRecorder.stop();
    }
}

async function enableVoiceActivation() {
    if (vadEnabled) {
        return true;
    }

    const participantId = localStorage.getItem('participant_id');
    if (!participantId) {
        throw new Error('participant_id ontbreekt. Herstart via het toestemmingsformulier.');
    }

    if (!window.vad || !window.vad.MicVAD) {
        throw new Error('VAD library not loaded.');
    }

    vadMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    vadController = await window.vad.MicVAD.new({
        stream: vadMicStream,
        startOnLoad: false,
        onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/',
        baseAssetPath: 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.29/dist/',
        onSpeechStart: async () => {
            if (!vadEnabled || isRecording) {
                return;
            }
            if (window.captureCurrentScreenshot) {
                window.screenshotBase64 = window.captureCurrentScreenshot();
            }
            await startRecording(vadMicStream);
        },
        onSpeechEnd: () => {
            if (!isRecording) {
                return;
            }
            currentChunkEndTime = new Date().toISOString();
            stopAudioChunkRecording();
        }
    });

    await vadController.start();
    vadEnabled = true;
    window.vadEnabled = vadEnabled;
    startScreenRecording(vadMicStream);
    startTimer();
    return true;
}

async function disableVoiceActivation(uploadScreenRecording = false) {
    if (!vadEnabled) {
        return false;
    }

    vadEnabled = false;
    window.vadEnabled = vadEnabled;
    stopTimer();

    if (vadController) {
        await vadController.pause();
        if (typeof vadController.destroy === 'function') {
            await vadController.destroy();
        }
        vadController = null;
        if (vadMicStream) {
            vadMicStream.getTracks().forEach(t => t.stop());
            vadMicStream = null;
        }
    }

    stopAudioChunkRecording();
    stopSessionScreenRecording(uploadScreenRecording);
    return false;
}

window.enableVoiceActivation = enableVoiceActivation;
window.disableVoiceActivation = disableVoiceActivation;