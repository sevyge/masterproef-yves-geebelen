'use strict';

const pipButton = document.getElementById('openPiP');

pipButton.addEventListener('click', async () => {
  if ('documentPictureInPicture' in window) {
    const pipWindow = await window.documentPictureInPicture.requestWindow({
      width: 300,
      height: 100
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
    recordButton.onclick = window.toggleRecording;

  } else {
    alert('Browser not supported');
  }
});

