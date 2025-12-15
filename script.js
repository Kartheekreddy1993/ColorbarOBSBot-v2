document.addEventListener("DOMContentLoaded", () => {
    const textContainer = document.getElementById('text-container');
    let lines = [];
    let currentLineIndex = 0;

    // Function to fetch the notepad file content
    async function fetchFileContent() {
        try {
            const response = await fetch('pending_jobs.txt');
            const text = await response.text();
            lines = text.split('\n').filter(line => line.trim() !== '');
        } catch (error) {
            console.error('Error fetching file content:', error);
        }
    }

    // Function to show a line with slide-in and slide-out effect
    function showLine() {
        if (lines.length === 0) return;

        const lineElement = document.createElement('div');
        lineElement.className = 'line slide-in';
        lineElement.textContent = lines[currentLineIndex];
        textContainer.appendChild(lineElement);

        setTimeout(() => {
            lineElement.classList.remove('slide-in');
            lineElement.classList.add('slide-out');

            lineElement.addEventListener('transitionend', () => {
                textContainer.removeChild(lineElement);
                currentLineIndex = (currentLineIndex + 1) % lines.length;
                showLine();
            }, { once: true });
        }, 3000); // Adjust the time based on how long you want the text to stay visible
    }

    // Function to continuously fetch the file and update the content
    async function updateContent() {
        await fetchFileContent();
        showLine();
        setInterval(async () => {
            await fetchFileContent();
        }, 5000); // Adjust the interval based on how frequently you want to check for file updates
    }

    // Initialize the content update
    updateContent();
});
