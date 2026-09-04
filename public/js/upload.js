// File Upload Logic

document.addEventListener('DOMContentLoaded', () => {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');
    const uploadText = document.getElementById('upload-text');
    
    if (!uploadArea || !fileInput) return;
    
    // Drag and Drop Events
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    // Click / File Input Event
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });
    
    async function handleFile(file) {
        if (!getToken()) {
            showToast('Please log in first to upload documents', true);
            setTimeout(() => { window.location.href = '/login'; }, 1500);
            return;
        }
        
        // Hide file input visually, show loader
        uploadStatus.classList.remove('hidden');
        uploadText.textContent = 'Uploading document...';
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            // Step 1: Upload the file
            const uploadRes = await fetch(`${window.API_BASE}/docs/upload`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: formData
            });
            
            const uploadData = await uploadRes.json();
            
            if (!uploadRes.ok) {
                throw new Error(uploadData.detail || 'Failed to upload file');
            }
            
            const documentId = uploadData.document_id;
            
            // Step 2: Trigger Gemini Analysis
            uploadText.textContent = 'Brewing your study session... (Analyzing document)';
            
            const analyzeRes = await fetch(`${window.API_BASE}/gemini/analyze-document/${documentId}`, {
                method: 'POST',
                headers: getAuthHeaders()
            });
            
            const analyzeData = await analyzeRes.json();
            
            if (!analyzeRes.ok) {
                throw new Error(analyzeData.detail || 'Analysis failed');
            }
            
            showToast('Document analyzed successfully!');
            
            // Redirect to Solve page
            setTimeout(() => {
                window.location.href = `/solve?doc=${documentId}`;
            }, 1000);
            
        } catch (err) {
            console.error(err);
            showToast(err.message, true);
            uploadStatus.classList.add('hidden');
        }
    }
});
