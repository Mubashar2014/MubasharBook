/* Share / print a receipt: render #receipt-card to PNG, then use the phone's
   share sheet (WhatsApp, etc.). Falls back to download + wa.me link. */
(function () {
    var btn = document.getElementById('share-receipt');
    var status = document.getElementById('share-status');
    if (!btn) return;

    function say(msg, isError) {
        if (!status) return;
        status.textContent = msg;
        status.style.color = isError ? '#A13D2E' : '#5A5748';
    }

    function download(blob, filename) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 5000);
    }

    function capture() {
        var card = document.getElementById('receipt-card');
        if (typeof html2canvas !== 'function') {
            return Promise.reject(new Error('Image renderer not loaded — check your connection and try Print instead.'));
        }
        return html2canvas(card, {
            scale: Math.max(2, window.devicePixelRatio || 1),
            backgroundColor: '#FFFDF6',
            useCORS: true,
            logging: false,
            windowWidth: card.scrollWidth,
        }).then(function (canvas) {
            return new Promise(function (resolve, reject) {
                if (canvas.toBlob) {
                    canvas.toBlob(function (blob) {
                        blob ? resolve(blob) : reject(new Error('Could not render the receipt image.'));
                    }, 'image/png');
                } else {
                    reject(new Error('Could not render the receipt image.'));
                }
            });
        });
    }

    btn.addEventListener('click', function () {
        var filename = btn.getAttribute('data-filename') || 'receipt.png';
        var wa = btn.getAttribute('data-wa') || '';
        btn.disabled = true;
        say('Preparing receipt image…');

        capture()
            .then(function (blob) {
                var file = null;
                try { file = new File([blob], filename, { type: 'image/png' }); } catch (e) { /* older Safari */ }

                if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
                    return navigator.share({ files: [file], title: 'Receipt' })
                        .then(function () { say('Receipt shared.'); });
                }

                download(blob, filename);
                if (wa) {
                    window.open(wa, '_blank', 'noopener');
                    say('Image downloaded — attach it in the WhatsApp chat that just opened.');
                } else {
                    say('Image downloaded — attach it in any chat or app.');
                }
            })
            .catch(function (err) {
                if (err && (err.name === 'AbortError' || err.name === 'NotAllowedError')) {
                    say('Sharing cancelled.');
                } else {
                    say((err && err.message) || 'Could not share the receipt.', true);
                }
            })
            .then(function () { btn.disabled = false; });
    });
})();
