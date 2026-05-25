/* killmail_v3.js — placeholder for future interactions */
(function() {
  'use strict';
  // Replace broken images
  document.querySelectorAll('img').forEach(function(img) {
    img.addEventListener('error', function() {
      if (this.onerror) { this.onerror = null; }
    });
  });
})();
