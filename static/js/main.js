if(window.location.hostname != 'localhost') {
    if(window.location.protocol == 'http:') {
      window.location.protocol = 'https:'
    }
}

$("#logo").on('click', function(){
  window.location.href = '/'
});