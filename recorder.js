'use strict';

let mediaRecorder, audioChunks = [], stream, isRecording = false;
let screenRecorder, screenChunks = [];
let lastChatResult = null;
const transcription = document.getElementById('transcription');
const ttsAudio = document.getElementById('ttsAudio');
const backendBaseUrl = backendUrl();

async function toggleRecording() {
    ttsAudio.pause();
    ttsAudio.currentTime = 0;
    if (!isRecording) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        if (window.videoStream) {
            const screenStream = new MediaStream([
                ...window.videoStream.getVideoTracks(),
                ...stream.getAudioTracks()
            ]);
            screenRecorder = new MediaRecorder(screenStream);
            screenChunks = [];
            screenRecorder.ondataavailable = e => {
                if (e.data.size > 0) screenChunks.push(e.data);
            };
            screenRecorder.onstop = async () => {
                const blob = new Blob(screenChunks, { type: 'video/webm' });
                try {
                    const participantId = localStorage.getItem('participant_id');
                    const formData = new FormData();
                    formData.append('video', blob, `screen-recording-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`);
                    formData.append('participant_id', participantId);
                    await fetch(`${backendBaseUrl}/upload-video`, {
                        method: 'POST',
                        body: formData
                    });
                    console.log('Video uploaded successfully');
                } catch (error) {
                    console.error('Error uploading video:', error);
                }
            };
            screenRecorder.start();
        }

        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());
            isRecording = false;
            if (window.recordButton) {
                window.recordButton.textContent = 'Klik om te praten';
            }

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

                    if (chatResult.response) {
                        const formDataTTS = new FormData();
                        formDataTTS.append('text', chatResult.response);
                        const ttsResponse = await fetch(`${backendBaseUrl}/tts-stream`, {
                            method: 'POST',
                            body: formDataTTS
                        });
                        const ttsBlob = await ttsResponse.blob();
                        const ttsObjectUrl = URL.createObjectURL(ttsBlob);
                        ttsAudio.src = ttsObjectUrl;
                        ttsAudio.play();
                    }
                }
            } catch (error) {
                transcription.textContent = 'Error: Server reageert niet.';
            }
        };
        mediaRecorder.start();
        isRecording = true;
        if (window.recordButton) {
            window.recordButton.textContent = 'Stop';
        }
    } else {
        mediaRecorder.stop();
        if (screenRecorder && screenRecorder.state !== 'inactive') {
            screenRecorder.stop();
        }
    }
}

window.toggleRecording = toggleRecording;