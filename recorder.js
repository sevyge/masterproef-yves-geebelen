'use strict';

let mediaRecorder, audioChunks = [], stream, isRecording = false;
let lastChatResult = null;
const transcription = document.getElementById('transcription');
const ttsAudio = document.getElementById('ttsAudio');

async function toggleRecording() {
    ttsAudio.pause();
    ttsAudio.currentTime = 0;
    if (!isRecording) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
                const response = await fetch('http://localhost:8000/transcribe', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                transcription.textContent = "Prompt: " + result.transcription;

                if (result.transcription) {
                    const formDataChat = new FormData();
                    formDataChat.append('prompt', result.transcription);
                    if (window.screenshotBase64) {
                        formDataChat.append('screenshot', window.screenshotBase64);
                    }
                    if (lastChatResult && lastChatResult.response_id) {
                        formDataChat.append('previous_response_id', lastChatResult.response_id);
                    }
                    const chatResponse = await fetch('http://localhost:8000/chat', {
                        method: 'POST',
                        body: formDataChat
                    });
                    const chatResult = await chatResponse.json();
                    lastChatResult = chatResult;
                    transcription.textContent += '\nChat model response: ' + chatResult.response;

                    if (chatResult.response) {
                        const formDataTTS = new FormData();
                        formDataTTS.append('text', chatResult.response);
                        const ttsResponse = await fetch('http://localhost:8000/tts-stream', {
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
    }
}

window.toggleRecording = toggleRecording;