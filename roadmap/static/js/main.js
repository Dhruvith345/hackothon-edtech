// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // Add roadmap timeline animation
    const timelineItems = document.querySelectorAll('.roadmap-timeline .card');
    
    timelineItems.forEach((item, index) => {
        item.style.opacity = '0';
        item.style.transform = 'translateX(-50px)';
        
        setTimeout(() => {
            item.style.transition = 'all 0.5s ease-out';
            item.style.opacity = '1';
            item.style.transform = 'translateX(0)';
        }, index * 200);
    });

    // Form validation
    const form = document.querySelector('form');
    if(form) {
        form.addEventListener('submit', function(e) {
            const skillsInput = document.getElementById('skills');
            if(skillsInput.value.split(',').filter(s => s.trim()).length < 3) {
                e.preventDefault();
                alert('Please enter at least 3 skills');
            }
        });
    }
});