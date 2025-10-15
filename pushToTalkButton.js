'use strict';

const pipButton = document.getElementById('openPiP');
let screenshotBase64 = null;
let video = null;

pipButton.addEventListener('click', async () => {
  try {
    const videoStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    video = document.createElement('video');
    video.srcObject = videoStream;
    video.play();

  } catch (err) {
    alert('Error: ' + err.message);
  }

  if ('documentPictureInPicture' in window) {
    const pipWindow = await window.documentPictureInPicture.requestWindow({
      width: 300,
      height: 100,
      disallowReturnToOpener: true
    });

    pipButton.disabled = true;
    pipButton.textContent = "Overlay Open";

    pipWindow.document.body.innerHTML = `
      <style>
        html, body { 
          height: 100%;
          margin: 0; 
        }
        button {
          width: 100%;
          height: 100%;
          font-size: 16px;
        }
      </style>
      <button id="recordButton">Klik om te praten</button>
    `;



    const recordButton = pipWindow.document.getElementById('recordButton');
    window.recordButton = recordButton;
    recordButton.onclick = () => {
      if (recordButton.textContent === 'Klik om te praten') {
        window.screenshotBase64 = takeScreenshot(video);
      }
      window.toggleRecording();
    };

    pipWindow.addEventListener('pagehide', () => {
      pipButton.disabled = false;
      pipButton.textContent = "Open Overlay";
      if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
      }
    });

  } else {
    alert('Browser not supported');
  }
});

function takeScreenshot(video) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  screenshotBase64 = canvas.toDataURL('image/png');
  return screenshotBase64;
}

