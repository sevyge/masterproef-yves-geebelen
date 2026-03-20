'use strict';

let mediaRecorder;
let audioChunks = [];
let stream;
let isRecording = false;
let screenRecorder, screenChunks = [];
let lastChatResult = null;
let vadEnabled = false;
let vadController = null;
let vadMicStream = null;
let shouldUploadScreenRecording = false;
const transcription = document.getElementById('transcription');
const ttsAudio = document.getElementById('ttsAudio');
const backendBaseUrl = backendUrl();

function setRecordButtonLabel(label) {
    if (window.recordButton) {
        window.recordButton.textContent = label;
    }
}

async function uploadScreenRecording(blob) {
    const participantId = localStorage.getItem('participant_id');
    const formData = new FormData();
    formData.append('video', blob, `screen-recording-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`);
    formData.append('participant_id', participantId);

    await fetch(`${backendBaseUrl}/upload-video`, {
        method: 'POST',
        body: formData
    });
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
            await uploadScreenRecording(blob);
            console.log('Video uploaded successfully');
        } catch (error) {
            console.error('Error uploading video:', error);
        } finally {
            shouldUploadScreenRecording = false;
        }
    };

    screenRecorder.start();
}

async function startRecording(sharedStream) {
    isRecording = true;
    stream = sharedStream || await navigator.mediaDevices.getUserMedia({ audio: true });

    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
    mediaRecorder.onstop = async () => {
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
            stopAudioChunkRecording();
        }
    });

    await vadController.start();
    vadEnabled = true;
    window.vadEnabled = vadEnabled;
    startScreenRecording(vadMicStream);
    setRecordButtonLabel('Beëindig onderzoek');
    return true;
}

async function disableVoiceActivation(uploadScreenRecording = false) {
    if (!vadEnabled) {
        return false;
    }

    vadEnabled = false;
    window.vadEnabled = vadEnabled;

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
    setRecordButtonLabel('Start onderzoek');
    return false;
}

window.enableVoiceActivation = enableVoiceActivation;
window.disableVoiceActivation = disableVoiceActivation;