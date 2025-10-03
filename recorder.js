let mediaRecorder, audioChunks = [], stream, isRecording = false;
const recordButton = document.getElementById('recordButton');
const transcription = document.getElementById('transcription');

recordButton.onclick = toggleRecording;

async function toggleRecording() {
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
                const audioBlob = new Blob(audioChunks);
                const formData = new FormData();
                formData.append('audio', audioBlob);
                const response = await fetch('http://localhost:8000/transcribe', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                transcription.textContent = result.transcription;
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