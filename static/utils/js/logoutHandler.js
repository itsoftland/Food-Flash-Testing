/**
 * logoutHandler.js
 * 
 * Clears localStorage when any element with the 'logout-link' class is clicked.
 * This ensures that JWT tokens and other session-related data are purged 
 * before the user is redirected to the logout URL.
 */
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        const logoutLinks = document.querySelectorAll('.logout-link');
        
        logoutLinks.forEach(function(link) {
            link.addEventListener('click', function(e) {
                // Clear all localStorage data
                console.log('Purging localStorage on logout...');
                localStorage.clear();
                
                // Also clear session storage just in case
                sessionStorage.clear();
            });
        });
    });
})();
