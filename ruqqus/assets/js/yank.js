// Yank Post

yank_postModal = function(id, author, comments, points, thumb, title, author_link, domain, timestamp) {

  // Passed data for modal

  document.getElementById("post-author").textContent = author;

  document.getElementById("post-comments").textContent = comments;

  document.getElementById("post-points").textContent = points;

  document.getElementById("post-thumb").src = thumb;

  document.getElementById("post-title").textContent = title;

  document.getElementById("post-author-url").href = author_link;

  document.getElementById("post-domain").textContent = domain;

  document.getElementById("post-timestamp").textContent = timestamp;
  
  document.getElementById("yank-post-form").action="/mod/take/"+id;

  document.getElementById("yankPostButton").onclick = function() {  

    this.innerHTML='<span class="spinner-border spinner-border-sm mr-2" role="status" aria-hidden="true"></span>Yanking post';  
    this.disabled = true; 
    document.getElementById("yank-post-form").submit();
  }

  // If not thumbnail exists, remove div that contains img tag

  if (thumb == "None" or thumb == null) {
     document.getElementById("post-thumb").classList.toggle("d-none");
  }

};

$('yankPostModal').on('hidden.bs.modal', function () {

  var thumb = document.getElementById("post-thumb");
  
  if (testElement.classList.contains(d-none)) {
      thumb.classList.toggle("d-none");
  }

});
