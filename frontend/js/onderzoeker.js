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

    document.addEventListener("keydown", function(e) {
        if (currentSegmentIndex < 0) return;
        
        const labelMap = { "1": "DK", "2": "PK", "3": "CK", "4": "DOM", "5": "NONE" };
        const label = labelMap[e.key];
        if (!label) return;
        
        e.preventDefault();
        
        const selectionInfo = getSelectedTextInfo();
        if (selectionInfo) {
            addAnnotation(selectionInfo.quote, selectionInfo.start, selectionInfo.end, label);
        }
    });

    document.getElementById("saveBtn").addEventListener("click", function() {
        saveAnnotations();
    });

    document.getElementById("toggleLlmAnnotations").addEventListener("change", function() {
        renderTranscript();
    });
}

async function loadParticipants() {
    try {
        const response = await fetch(`${backendUrl()}/researcher/participants`);
        if (!response.ok) return;

        const participants = await response.json();
        let optionsHtml = '<option value="">Selecteer...</option>';
        for (let i = 0; i < participants.length; i++) {
            optionsHtml += `<option value="${participants[i]}">Participant ${participants[i]}</option>`;
        }
        document.getElementById("participantSelect").innerHTML = optionsHtml;
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
    let html = "";
    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        const isActive = (i === currentSegmentIndex);
        const count = segment.human_annotaties.length;
        const badgeHtml = count > 0
            ? `<span class="badge ${isActive ? 'bg-light text-dark' : 'bg-secondary text-white'} rounded-circle">${count}</span>`
            : `<i class="bi bi-circle ${isActive ? 'text-white-50' : 'text-muted'}"></i>`;
            
        html += `
            <div class="list-group-item list-group-item-action p-3 ${isActive ? 'active bg-danger border-danger' : ''}" 
                 style="cursor: pointer;" onclick="selectSegment(${i})">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="fw-bold">Segment ${segment.segment_id}</span>
                    ${badgeHtml}
                </div>
                <small class="d-block text-wrap ${isActive ? '' : 'text-muted'}">${segment.transcript || ""}</small>
            </div>
        `;
    }
    document.getElementById("segmentsList").innerHTML = html;
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
    const screenshotViewer = document.getElementById("screenshotViewer");
    
    if (index < 0 || index >= segments.length) {
        document.getElementById("transcriptContainer").innerHTML = "";
        screenshotViewer.innerHTML = `
            <span class="text-muted" id="screenshotPlaceholder">
                <i class="bi bi-image fs-1 d-block text-center"></i>Screenshot context
            </span>
        `;
        return;
    }
    
    renderTranscript();
    renderAnnotationsList();
    
    const segment = segments[index];
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

function getSelectedTextInfo() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return null;
    
    const range = selection.getRangeAt(0);
    const container = document.getElementById("transcriptContainer");
    
    if (!container.contains(range.commonAncestorContainer)) return null;
    
    const selectedText = range.toString().trim();
    if (!selectedText) return null;
    
    const preSelectionRange = range.cloneRange();
    preSelectionRange.selectNodeContents(container);
    preSelectionRange.setEnd(range.startContainer, range.startOffset);
    
    const start = preSelectionRange.toString().length;
    const end = start + selectedText.length;
    
    return {
        quote: range.toString(),
        start: start,
        end: end
    };
}

function addAnnotation(quote, start, end, label) {
    const segment = segments[currentSegmentIndex];
    segment.human_annotaties.push({
        label: label,
        quote: quote,
        start: start,
        end: end
    });
    
    window.getSelection().removeAllRanges();
    renderTranscript();
    renderAnnotationsList();
    renderSegments();
}

function deleteAnnotation(idx) {
    if (currentSegmentIndex < 0) return;
    
    const segment = segments[currentSegmentIndex];
    segment.human_annotaties.splice(idx, 1);
    
    renderTranscript();
    renderAnnotationsList();
    renderSegments();
}

function getCategoryColor(label) {
    if (label === "DK") return "warning";
    if (label === "PK") return "primary";
    if (label === "CK") return "success";
    if (label === "DOM") return "danger";
    return "secondary";
}

function escapeHtml(txt) {
    return txt
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function renderTranscript() {
    const transcriptContainer = document.getElementById("transcriptContainer");
    if (currentSegmentIndex < 0) {
        transcriptContainer.innerHTML = "";
        return;
    }
    
    const segment = segments[currentSegmentIndex];
    const text = segment.transcript || "";
    
    const charClasses = new Array(text.length).fill("");
    
    const humanAnns = segment.human_annotaties || [];
    for (let i = 0; i < humanAnns.length; i++) {
        const ann = humanAnns[i];
        const color = getCategoryColor(ann.label);
        for (let j = ann.start; j < ann.end; j++) {
            if (j >= 0 && j < text.length) {
                charClasses[j] += ` bg-${color}-subtle border-bottom border-${color}`;
            }
        }
    }
    
    const showLlm = document.getElementById("toggleLlmAnnotations").checked;
    if (showLlm && segment.llm_annotaties) {
        const llmAnns = segment.llm_annotaties;
        for (let i = 0; i < llmAnns.length; i++) {
            const ann = llmAnns[i];
            const color = getCategoryColor(ann.label);
            for (let j = ann.start; j < ann.end; j++) {
                if (j >= 0 && j < text.length) {
                    charClasses[j] += ` border-bottom border-${color} border-dashed border-2`;
                }
            }
        }
    }
    
    let html = "";
    let currentChunk = "";
    let currentClass = charClasses[0] || "";
    
    for (let i = 0; i < text.length; i++) {
        if (charClasses[i] !== currentClass) {
            if (currentClass.trim()) {
                html += `<span class="${currentClass.trim()}">${escapeHtml(currentChunk)}</span>`;
            } else {
                html += escapeHtml(currentChunk);
            }
            currentChunk = "";
            currentClass = charClasses[i];
        }
        currentChunk += text[i];
    }
    
    if (currentChunk) {
        if (currentClass.trim()) {
            html += `<span class="${currentClass.trim()}">${escapeHtml(currentChunk)}</span>`;
        } else {
            html += escapeHtml(currentChunk);
        }
    }
    
    transcriptContainer.innerHTML = html;
}

function renderAnnotationsList() {
    if (currentSegmentIndex < 0) return;
    
    const segment = segments[currentSegmentIndex];
    const annotations = segment.human_annotaties || [];
    let html = "";
    
    for (let i = 0; i < annotations.length; i++) {
        const ann = annotations[i];
        const color = getCategoryColor(ann.label);
        const textClass = ann.label === "DK" ? "text-dark" : "text-white";
        
        html += `
            <div class="card mb-2 border-light shadow-sm">
                <div class="card-body p-2 d-flex align-items-center justify-content-between">
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge bg-${color} ${textClass}">${ann.label}</span>
                        <span class="small font-monospace text-truncate" style="max-width: 180px;">"${escapeHtml(ann.quote)}"</span>
                    </div>
                    <button class="btn btn-link text-danger p-0 border-0" onclick="deleteAnnotation(${i})">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }
    document.getElementById("annotationsList").innerHTML = html;
}

window.deleteAnnotation = deleteAnnotation;
window.selectSegment = selectSegment;

async function saveAnnotations() {
    if (!currentParticipantId || segments.length === 0) return;
    
    const saveBtn = document.getElementById("saveBtn");
    const originalText = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Opslaan...';

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${currentParticipantId}/annotations`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(segments)
        });
        
        if (response.ok) {
            alert("Annotaties succesvol opgeslagen!");
        } else {
            alert("Fout bij het opslaan van annotaties.");
        }
    } catch (error) {
        console.error("Error saving annotations:", error);
        alert("Netwerkfout bij het opslaan.");
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    }
}
