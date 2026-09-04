// Practice logic

document.addEventListener('DOMContentLoaded', async () => {
    if (!getToken()) {
        window.location.href = '/login';
        return;
    }
    
    await loadDocuments();
    
    document.getElementById('practice-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const docId = document.getElementById('doc-select').value;
        const diff = document.getElementById('diff-select').value;
        const num = document.getElementById('num-select').value;
        
        if (!docId) {
            showToast('Please select a document', true);
            return;
        }
        
        const btn = document.getElementById('generate-btn');
        btn.innerHTML = '<div class="loader"></div>';
        btn.disabled = true;
        
        try {
            const res = await fetch(`${window.API_BASE}/gemini/generate-practice`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({
                    document_id: parseInt(docId),
                    num_questions: parseInt(num),
                    difficulty: diff
                })
            });
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to generate practice');
            
            renderQuestions(data.questions);
            
            document.getElementById('settings-card').style.display = 'none';
            document.getElementById('results-container').style.display = 'block';
            
        } catch (err) {
            showToast(err.message, true);
            btn.innerHTML = '<span class="material-symbols-outlined">auto_awesome</span> Generate Practice';
            btn.disabled = false;
        }
    });
});

async function loadDocuments() {
    try {
        const res = await fetch(`${window.API_BASE}/docs/history`, {
            headers: getAuthHeaders()
        });
        const data = await res.json();
        
        const select = document.getElementById('doc-select');
        select.innerHTML = '';
        
        if (data.history && data.history.length > 0) {
            const completedDocs = data.history.filter(d => d.analysis_status === 'completed');
            
            if (completedDocs.length === 0) {
                select.innerHTML = '<option value="" disabled selected>No analyzed documents available</option>';
                document.getElementById('generate-btn').disabled = true;
                return;
            }
            
            completedDocs.forEach(doc => {
                const opt = document.createElement('option');
                opt.value = doc.id;
                opt.textContent = doc.title || 'Untitled Document';
                select.appendChild(opt);
            });
        } else {
            select.innerHTML = '<option value="" disabled selected>No documents found</option>';
            document.getElementById('generate-btn').disabled = true;
        }
    } catch (err) {
        console.error(err);
    }
}

function renderQuestions(questions) {
    const list = document.getElementById('questions-list');
    list.innerHTML = '';
    
    questions.forEach((q, idx) => {
        const div = document.createElement('div');
        div.className = 'practice-question';
        
        div.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <h3 style="margin-bottom: 1rem;">Question ${idx + 1}</h3>
                <span style="font-size: 0.8rem; background: rgba(92, 67, 59, 0.1); padding: 0.2rem 0.5rem; border-radius: var(--radius-full);">${q.question_type || 'Practice'}</span>
            </div>
            <p style="font-size: 1.1rem; line-height: 1.5; margin-bottom: 1.5rem;">${q.question_text}</p>
            
            <button class="btn btn-secondary reveal-btn" style="font-size: 0.9rem; padding: 0.5rem 1rem;">
                Reveal Answer & Solution
            </button>
            
            <div class="practice-answer">
                <h4 style="margin-bottom: 0.5rem; color: var(--clr-espresso);">Answer:</h4>
                <p style="margin-bottom: 1rem; font-weight: 500;">${q.answer || 'No direct answer provided.'}</p>
                <h4 style="margin-bottom: 0.5rem; color: var(--clr-espresso);">Solution Steps:</h4>
                <p style="line-height: 1.5;">${q.solution}</p>
            </div>
        `;
        
        const revealBtn = div.querySelector('.reveal-btn');
        const answerDiv = div.querySelector('.practice-answer');
        
        revealBtn.addEventListener('click', () => {
            if (answerDiv.style.display === 'block') {
                answerDiv.style.display = 'none';
                revealBtn.textContent = 'Reveal Answer & Solution';
            } else {
                answerDiv.style.display = 'block';
                revealBtn.textContent = 'Hide Answer & Solution';
            }
        });
        
        list.appendChild(div);
    });
}
