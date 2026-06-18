let currentParticipantId = null;
let segments = [];
let currentSegmentIndex = -1;

document.addEventListener("DOMContentLoaded", function() {
    loadParticipants();
    setupEventListeners();
});

function setupEventListeners() {
    document.getElementById("participantSelect").addEventListener("change", function(e) {
        const participantId = e.target.value;
        if (participantId) {
            loadParticipantData(participantId);
        } else {
            clearWorkspace();
        }
    });
}

async function loadParticipants() {
    try {
        const response = await fetch(`${backendUrl()}/researcher/participants`);
        if (!response.ok) {
            console.error("Failed to fetch participants list");
            return;
        }

        const participants = await response.json();
        const select = document.getElementById("participantSelect");
        
        select.innerHTML = '<option value="">Selecteer...</option>';
        for (let i = 0; i < participants.length; i++) {
            const participantId = participants[i];
            const option = document.createElement("option");
            option.value = participantId;
            option.textContent = `Participant ${participantId}`;
            select.appendChild(option);
        }
    } catch (error) {
        console.error("Error loading participants:", error);
    }
}

async function loadParticipantData(participantId) {
    currentParticipantId = participantId;
    segments = [];
    currentSegmentIndex = -1;
    clearWorkspace();

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${participantId}/transcript`);
        if (!response.ok) {
            console.error("Failed to fetch participant transcript");
            return;
        }

        segments = await response.json();
        renderSegments();
        
        if (segments.length > 0) {
            selectSegment(0);
        }
    } catch (error) {
        console.error("Error loading participant data:", error);
    }
}

function clearWorkspace() {
    document.getElementById("segmentsList").innerHTML = "";
    document.getElementById("progressIndicator").textContent = "0 / 0";
    document.getElementById("transcriptContainer").innerHTML = "";
    document.getElementById("screenshotViewer").innerHTML = `
        <span class="text-muted" id="screenshotPlaceholder">
            <i class="bi bi-image fs-1 d-block text-center"></i>Screenshot context
        </span>
    `;
    document.getElementById("annotationsList").innerHTML = "";
}

function renderSegments() {
    const segmentsList = document.getElementById("segmentsList");
    segmentsList.innerHTML = "";
    
    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        const isActive = (i === currentSegmentIndex);
        const div = document.createElement("div");
        
        div.className = `list-group-item list-group-item-action p-3 ${isActive ? 'active bg-danger border-danger' : ''}`;
        div.style.cursor = "pointer";
        div.addEventListener("click", function() {
            selectSegment(i);
        });
        
        const count = segment.human_annotaties.length;
        const badgeHtml = count > 0
            ? `<span class="badge ${isActive ? 'bg-light text-dark' : 'bg-secondary text-white'} rounded-circle">${count}</span>`
            : `<i class="bi bi-circle ${isActive ? 'text-white-50' : 'text-muted'}"></i>`;
        
        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="fw-bold">Segment ${segment.segment_id}</span>
                ${badgeHtml}
            </div>
            <small class="d-block text-wrap ${isActive ? '' : 'text-muted'}">${segment.transcript || ""}</small>
        `;
        
        segmentsList.appendChild(div);
    }
    
    updateProgress();
}

function updateProgress() {
    let codedCount = 0;
    for (let i = 0; i < segments.length; i++) {
        if (segments[i].human_annotaties.length > 0) {
            codedCount++;
        }
    }
    document.getElementById("progressIndicator").textContent = `${codedCount} / ${segments.length}`;
}

function selectSegment(index) {
    currentSegmentIndex = index;
    renderSegments();
    loadSegmentDetails(index);
}

function loadSegmentDetails(index) {
    const transcriptContainer = document.getElementById("transcriptContainer");
    const screenshotViewer = document.getElementById("screenshotViewer");
    
    if (index < 0 || index >= segments.length) {
        transcriptContainer.innerHTML = "";
        screenshotViewer.innerHTML = `
            <span class="text-muted" id="screenshotPlaceholder">
                <i class="bi bi-image fs-1 d-block text-center"></i>Screenshot context
            </span>
        `;
        return;
    }
    
    const segment = segments[index];
    transcriptContainer.textContent = segment.transcript || "";
    
    if (segment.screenshot_bestandsnaam) {
        const imgUrl = `${backendUrl()}/researcher/participant/${currentParticipantId}/screenshot/${segment.screenshot_bestandsnaam}`;
        screenshotViewer.innerHTML = `<img src="${imgUrl}" alt="Screenshot Context" class="img-fluid border rounded" style="max-height: 100%; max-width: 100%; object-fit: contain;">`;
    } else {
        screenshotViewer.innerHTML = `
            <span class="text-muted" id="screenshotPlaceholder">
                <i class="bi bi-image fs-1 d-block text-center"></i>Geen screenshot beschikbaar
            </span>
        `;
    }
}
