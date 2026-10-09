function uploadMedia(inputElement, targetFieldPath, previewImgId) {
  var file = inputElement.files ? inputElement.files[0] : null;
  if (!file) return;
  var form = new FormData();
  form.append('file', file);
  fetch('/api/upload', { method: 'POST', body: form })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var url = data.url || '';
      var targetInput = document.getElementById(targetFieldPath);
      if (targetInput) targetInput.value = url;
      if (previewImgId) {
        var img = document.getElementById(previewImgId);
        if (img) img.src = url;
      }
    })
    .catch(function(e) { console.error('Upload error', e); });
}

function deleteMedia(targetFieldPath, previewImgId, fallbackSrc) {
  var targetInput = document.getElementById(targetFieldPath);
  if (targetInput) {
    targetInput.value = '';
  }
  if (previewImgId) {
    var img = document.getElementById(previewImgId);
    if (img) img.src = fallbackSrc || '/assets/letuchka_nurlan.jpg';
  }
}
