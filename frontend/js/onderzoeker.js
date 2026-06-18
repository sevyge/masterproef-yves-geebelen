let currentParticipantId = null;
let segments = [];
let currentSegmentIndex = -1;
let activeSelection = null;

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
        
        if (activeSelection) {
            addAnnotation(activeSelection.quote, activeSelection.start, activeSelection.end, label);
            hideSelectionPopup();
        }
    });

    document.getElementById("saveBtn").addEventListener("click", function() {
        saveAnnotations();
    });

    document.getElementById("toggleLlmAnnotations").addEventListener("change", function() {
        renderTranscript();
    });

    document.getElementById("transcriptContainer").addEventListener("pointerup", function() {
        handleTextSelection();
    });

    document.getElementById("selectionPopup").addEventListener("click", function(e) {
        const button = e.target.closest(".popup-btn");
        if (!button) return;
        
        const label = button.getAttribute("data-label");
        if (activeSelection) {
            addAnnotation(activeSelection.quote, activeSelection.start, activeSelection.end, label);
        }
        hideSelectionPopup();
    });

    document.addEventListener("pointerdown", function(e) {
        const popup = document.getElementById("selectionPopup");
        const container = document.getElementById("transcriptContainer");
        if (popup && !popup.contains(e.target) && !container.contains(e.target)) {
            hideSelectionPopup();
        }
    });
}

async function loadParticipants() {
    try {
        const response = await fetch(`${backendUrl()}/researcher/participants`);
        if (!response.ok) return;

        const participants = await response.json();
        let optionsHtml = '';
        for (let i = 0; i < participants.length; i++) {
            optionsHtml += `<option value="${participants[i]}">Participant ${participants[i]}</option>`;
        }
        const selectEl = document.getElementById("participantSelect");
        selectEl.innerHTML = optionsHtml;

        // Auto-select the first participant by default
        if (participants.length > 0) {
            selectEl.value = participants[0];
            loadParticipantData(participants[0]);
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

    const spinner = '<div class="text-center py-5"><div class="spinner-border spinner-border-sm text-secondary" role="status"></div></div>';
    document.getElementById("segmentsList").innerHTML = spinner;
    document.getElementById("transcriptContainer").innerHTML = spinner;
    document.getElementById("screenshotViewer").innerHTML = spinner;

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${participantId}/transcript`);
        if (!response.ok) {
            console.error("Failed to fetch participant transcript");
            clearWorkspace();
            return;
        }

        segments = await response.json();
        for (let i = 0; i < segments.length; i++) {
            // Normalize newlines to spaces so Range.toString() matches textContent
            segments[i].transcript = (segments[i].transcript || "").replace(/\n/g, " ");
            if (!segments[i].human_annotaties) segments[i].human_annotaties = [];
            if (!segments[i].llm_annotaties) segments[i].llm_annotaties = [];
        }
        
        renderSegments();
        
        if (segments.length > 0) {
            selectSegment(0);
        }
    } catch (error) {
        console.error("Error loading participant data:", error);
        clearWorkspace();
    }
}

function renderScreenshotPlaceholder(message) {
    return `
        <span class="text-muted" id="screenshotPlaceholder">
            <i class="bi bi-image fs-1 d-block text-center"></i>${message}
        </span>
    `;
}

function clearWorkspace() {
    hideSelectionPopup();
    document.getElementById("segmentsList").innerHTML = "";
    document.getElementById("progressIndicator").textContent = "0 / 0";
    document.getElementById("transcriptContainer").innerHTML = "";
    document.getElementById("screenshotViewer").innerHTML = renderScreenshotPlaceholder("Screenshot context");
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
    hideSelectionPopup();
    currentSegmentIndex = index;
    renderSegments();
    loadSegmentDetails(index);
}

function loadSegmentDetails(index) {
    const screenshotViewer = document.getElementById("screenshotViewer");
    
    if (index < 0 || index >= segments.length) {
        document.getElementById("transcriptContainer").innerHTML = "";
        screenshotViewer.innerHTML = renderScreenshotPlaceholder("Screenshot context");
        return;
    }
    
    renderTranscript();
    renderAnnotationsList();
    
    const segment = segments[index];
    if (segment.screenshot_bestandsnaam) {
        const imgUrl = `${backendUrl()}/researcher/participant/${currentParticipantId}/screenshot/${segment.screenshot_bestandsnaam}`;
        screenshotViewer.innerHTML = `<img src="${imgUrl}" alt="Screenshot Context" class="img-fluid border rounded" style="max-height: 100%; max-width: 100%; object-fit: contain;">`;
    } else {
        screenshotViewer.innerHTML = renderScreenshotPlaceholder("Geen screenshot beschikbaar");
    }
}

function getSelectedTextInfo() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return null;
    
    const range = selection.getRangeAt(0);
    const container = document.getElementById("transcriptContainer");
    
    if (!container.contains(range.commonAncestorContainer)) return null;
    
    const fullText = range.toString();
    const trimmedText = fullText.trim();
    if (!trimmedText) return null;
    
    const preSelectionRange = range.cloneRange();
    preSelectionRange.selectNodeContents(container);
    preSelectionRange.setEnd(range.startContainer, range.startOffset);
    
    const leadingSpaces = fullText.match(/^\s*/)[0].length;
    const trailingSpaces = fullText.match(/\s*$/)[0].length;
    
    const start = preSelectionRange.toString().length + leadingSpaces;
    const end = preSelectionRange.toString().length + fullText.length - trailingSpaces;
    
    return {
        quote: trimmedText,
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

function handleTextSelection() {
    activeSelection = getSelectedTextInfo();
    const popup = document.getElementById("selectionPopup");
    if (!activeSelection) {
        hideSelectionPopup();
        return;
    }

    const selection = window.getSelection();
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    popup.classList.remove("d-none");

    const popupWidth = popup.offsetWidth || 230;
    const popupHeight = popup.offsetHeight || 42;

    popup.style.left = `${rect.left + window.scrollX + (rect.width / 2) - (popupWidth / 2)}px`;
    popup.style.top = `${rect.top + window.scrollY - popupHeight - 8}px`;
}

function hideSelectionPopup() {
    activeSelection = null;
    const popup = document.getElementById("selectionPopup");
    if (popup) {
        popup.classList.add("d-none");
    }
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

function wrapChunk(chunk, humanClass, llmClass) {
    let html = escapeHtml(chunk);
    if (llmClass) html = `<span class="${llmClass}">${html}</span>`;
    if (humanClass) html = `<span class="${humanClass}">${html}</span>`;
    return html;
}

function renderTranscript() {
    const transcriptContainer = document.getElementById("transcriptContainer");
    if (currentSegmentIndex < 0) {
        transcriptContainer.innerHTML = "";
        return;
    }
    
    const segment = segments[currentSegmentIndex];
    const text = segment.transcript || "";
    
    const humanClasses = new Array(text.length).fill("");
    const llmClasses = new Array(text.length).fill("");
    
    const humanAnns = segment.human_annotaties || [];
    for (let i = 0; i < humanAnns.length; i++) {
        const ann = humanAnns[i];
        const color = getCategoryColor(ann.label);
        for (let j = ann.start; j < ann.end; j++) {
            if (j >= 0 && j < text.length) {
                humanClasses[j] = `bg-${color}-subtle border-bottom border-${color}`;
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
                    llmClasses[j] = `border-bottom border-${color} border-dashed border-2`;
                }
            }
        }
    }
    
    let html = "";
    let currentChunk = "";
    let currentHuman = humanClasses[0] || "";
    let currentLlm = llmClasses[0] || "";
    
    for (let i = 0; i < text.length; i++) {
        if (humanClasses[i] !== currentHuman || llmClasses[i] !== currentLlm) {
            html += wrapChunk(currentChunk, currentHuman, currentLlm);
            currentChunk = "";
            currentHuman = humanClasses[i];
            currentLlm = llmClasses[i];
        }
        currentChunk += text[i];
    }
    
    if (currentChunk) {
        html += wrapChunk(currentChunk, currentHuman, currentLlm);
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
