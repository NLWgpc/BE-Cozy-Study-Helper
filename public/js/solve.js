// Solve Page Logic

let currentQuestions = [];
let currentIndex = 0;
let currentDocument = null;

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Get document ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const docId = urlParams.get('doc');
    
    if (!docId) {
        window.location.href = '/';
        return;
    }
    
    await loadDocumentData(docId);
    
    // Set up listeners
    document.getElementById('btn-prev').addEventListener('click', () => navigateQuestion(-1));
    document.getElementById('btn-next').addEventListener('click', () => navigateQuestion(1));
    
    document.getElementById('chat-form').addEventListener('submit', handleChatSubmit);
});

async function loadDocumentData(docId) {
    try {
        const res = await fetch(`${window.API_BASE}/docs/${docId}`, {
            headers: getAuthHeaders()
        });
        
        if (!res.ok) {
            throw new Error('Failed to load document');
        }
        
        const data = await res.json();
        currentDocument = data.document;
        currentQuestions = data.questions;
        
        // Render Document Viewer
        document.getElementById('doc-title').textContent = currentDocument.title || 'Document';
        const viewerContainer = document.getElementById('viewer-container');
        
        if (currentDocument.file_type === 'application/pdf') {
            viewerContainer.innerHTML = `<iframe src="${currentDocument.file_url}" class="document-viewer"></iframe>`;
        } else {
            viewerContainer.innerHTML = `<img src="${currentDocument.file_url}" class="document-viewer">`;
        }
        
        // Render first question
        if (currentQuestions.length > 0) {
            currentIndex = 0;
            renderCurrentQuestion();
        } else {
            document.getElementById('q-text').textContent = 'No questions detected in this document.';
        }
        
    } catch (err) {
        showToast(err.message, true);
    }
}

function renderCurrentQuestion() {
    if (currentQuestions.length === 0) return;
    
    const q = currentQuestions[currentIndex];
    
    document.getElementById('q-number').textContent = `Question ${q.question_number || (currentIndex + 1)}`;
    document.getElementById('q-counter').textContent = `${currentIndex + 1} / ${currentQuestions.length}`;
    document.getElementById('q-text').textContent = q.question_text;
    
    // Parse steps
    const stepsList = document.getElementById('q-steps');
    stepsList.innerHTML = '';
    
    try {
        const steps = JSON.parse(q.steps);
        if (Array.isArray(steps) && steps.length > 0) {
            steps.forEach((step, idx) => {
                const li = document.createElement('li');
                li.className = 'step-item';
                li.innerHTML = `<strong>Step ${idx + 1}:</strong> ${step}`;
                stepsList.appendChild(li);
            });
        } else {
            stepsList.innerHTML = '<li class="step-item text-muted">No steps provided.</li>';
        }
    } catch (e) {
        stepsList.innerHTML = `<li class="step-item">${q.steps}</li>`;
    }
    
    // Answer
    const answerBox = document.getElementById('q-answer-box');
    if (q.answer) {
        answerBox.classList.remove('hidden');
        document.getElementById('q-answer').textContent = q.answer;
    } else {
        answerBox.classList.add('hidden');
    }
    
    // Update buttons
    document.getElementById('btn-prev').disabled = currentIndex === 0;
    document.getElementById('btn-next').disabled = currentIndex === currentQuestions.length - 1;
    
    // Reset Chat
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.innerHTML = `
        <div class="chat-msg msg-bot">
            Let's work on Question ${q.question_number} together. What do you need help with?
        </div>
    `;
}

function navigateQuestion(dir) {
    const newIndex = currentIndex + dir;
    if (newIndex >= 0 && newIndex < currentQuestions.length) {
        currentIndex = newIndex;
        renderCurrentQuestion();
    }
}

async function handleChatSubmit(e) {
    e.preventDefault();
    const input = document.getElementById('chat-input-text');
    const msg = input.value.trim();
    if (!msg) return;
    
    // Add user message to UI
    appendMessage(msg, 'user');
    input.value = '';
    
    const q = currentQuestions[currentIndex];
    
    // Add loading bot message
    const loadingId = 'loading-' + Date.now();
    appendMessage('<div class="loader" style="width: 16px; height: 16px; border-top-color: var(--clr-espresso);"></div>', 'bot', loadingId);
    
    try {
        const res = await fetch(`${window.API_BASE}/gemini/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                document_id: currentDocument.id,
                question_id: q.id,
                message: msg
            })
        });
        
        const data = await res.json();
        
        // Remove loading message
        document.getElementById(loadingId)?.remove();
        
        if (res.ok) {
            appendMessage(data.reply, 'bot');
        } else {
            appendMessage('Sorry, I ran into an error processing that.', 'bot');
            showToast(data.detail, true);
        }
        
    } catch (err) {
        document.getElementById(loadingId)?.remove();
        appendMessage('Network error communicating with Gemini.', 'bot');
    }
}

function appendMessage(content, role, id = null) {
    const chatMessages = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `chat-msg msg-${role}`;
    if (id) div.id = id;
    
    // Simple markdown replacement for bold text
    const formattedContent = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    div.innerHTML = formattedContent;
    
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}
