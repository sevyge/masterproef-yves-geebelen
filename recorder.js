let mediaRecorder, audioChunks = [], stream, isRecording = false;
let lastChatResult = null;
const recordButton = document.getElementById('recordButton');
const transcription = document.getElementById('transcription');
const ttsAudio = document.getElementById('ttsAudio');

recordButton.onclick = toggleRecording;

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
            recordButton.textContent = 'Record';
            isRecording = false;

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
                        const encodedText = encodeURIComponent(chatResult.response);
                        ttsAudio.src = `http://localhost:8000/tts-stream/${encodedText}`;
                        ttsAudio.play();
                    }
                }
            } catch (error) {
                transcription.textContent = 'Error: Server not responding';
            }
        };
        mediaRecorder.start();
        recordButton.textContent = 'Stop';
        isRecording = true;
    } else {
        mediaRecorder.stop();
    }
}