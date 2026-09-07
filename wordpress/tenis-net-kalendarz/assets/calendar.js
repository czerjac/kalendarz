(function(){
  'use strict';

  function normalize(value){
    return (value || '').toString().trim().toLocaleLowerCase('pl-PL');
  }

  function parseDate(value){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
    var p=value.split('-');
    return new Date(Number(p[0]), Number(p[1])-1, Number(p[2]), 12, 0, 0, 0);
  }

  function startOfToday(){
    var d=new Date();
    d.setHours(12,0,0,0);
    return d;
  }

  function init(root){
    var filters={};
    root.querySelectorAll('[data-tnk-filter]').forEach(function(el){filters[el.getAttribute('data-tnk-filter')]=el;});
    var reset=root.querySelector('[data-tnk-reset]');
    var count=root.querySelector('[data-tnk-count]');
    var empty=root.querySelector('[data-tnk-empty]');
    var tableItems=Array.prototype.slice.call(root.querySelectorAll('.tnk-table [data-tnk-item]'));
    var cardItems=Array.prototype.slice.call(root.querySelectorAll('.tnk-cards [data-tnk-item]'));

    function matches(item){
      var search=normalize(filters.search ? filters.search.value : '');
      var period=filters.period ? filters.period.value : 'all';
      var woj=normalize(filters.wojewodztwo ? filters.wojewodztwo.value : '');
      var org=normalize(filters.organizacja ? filters.organizacja.value : '');
      var cycle=normalize(filters.cykl ? filters.cykl.value : '');
      var game=normalize(filters.rodzaj ? filters.rodzaj.value : '');

      if(search && normalize(item.dataset.search).indexOf(search)===-1) return false;
      if(woj && normalize(item.dataset.wojewodztwo)!==woj) return false;
      if(org && normalize(item.dataset.organizacja)!==org) return false;
      if(cycle && normalize(item.dataset.cykl)!==cycle) return false;
      if(game){
        var games=normalize(item.dataset.rodzaje).split('|').filter(Boolean);
        if(games.indexOf(game)===-1) return false;
      }

      if(period !== 'all'){
        var start=parseDate(item.dataset.start);
        var end=parseDate(item.dataset.end) || start;
        var today=startOfToday();
        var max=new Date(today.getTime());
        max.setDate(max.getDate()+Number(period));
        if(end && end < today) return false;
        if(start && start > max) return false;
      }
      return true;
    }

    function hideAttachedDetail(item){
      if(item.tagName==='TR'){
        var next=item.nextElementSibling;
        if(next && next.matches('[data-tnk-detail]')){
          next.hidden=true;
          var btn=item.querySelector('[data-tnk-toggle]');
          if(btn){btn.setAttribute('aria-expanded','false');btn.textContent='Szczegóły';}
        }
      } else {
        var detail=item.querySelector('[data-tnk-detail]');
        if(detail) detail.hidden=true;
        var btn=item.querySelector('[data-tnk-toggle]');
        if(btn){btn.setAttribute('aria-expanded','false');btn.textContent='Szczegóły';}
      }
    }

    function apply(){
      var visible=0;
      tableItems.forEach(function(item){
        var ok=matches(item);
        item.classList.toggle('tnk-item-hidden',!ok);
        if(!ok) hideAttachedDetail(item);
        if(ok) visible++;
      });
      cardItems.forEach(function(item){
        var ok=matches(item);
        item.classList.toggle('tnk-item-hidden',!ok);
        if(!ok) hideAttachedDetail(item);
      });
      if(count) count.textContent=String(visible);
      if(empty) empty.hidden=visible!==0;
    }

    Object.keys(filters).forEach(function(key){
      filters[key].addEventListener(key==='search' ? 'input' : 'change',apply);
    });

    if(reset){
      reset.addEventListener('click',function(){
        Object.keys(filters).forEach(function(key){
          if(key==='period') filters[key].value='30'; else filters[key].value='';
        });
        apply();
      });
    }

    root.addEventListener('click',function(event){
      var button=event.target.closest('[data-tnk-toggle]');
      if(!button || !root.contains(button)) return;
      var target=document.getElementById(button.getAttribute('data-tnk-toggle'));
      if(!target) return;
      var isOpen=!target.hidden;
      target.hidden=isOpen;
      button.setAttribute('aria-expanded',isOpen ? 'false' : 'true');
      button.textContent=isOpen ? 'Szczegóły' : 'Zwiń';
    });

    apply();
  }

  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('[data-tnk-calendar]').forEach(init);
  });
})();
