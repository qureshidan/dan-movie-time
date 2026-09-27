'use strict';
const $=id=>document.getElementById(id);
// Each screen keeps its own layout preference; TV WebViews vary in their user agent.
let tvLayout=/Android/i.test(navigator.userAgent)&&!/Mobile/i.test(navigator.userAgent)||/Android TV|GoogleTV|AFT|SmartTV/i.test(navigator.userAgent);
try{const saved=localStorage.getItem('movie-time-tv-layout');if(saved!==null)tvLayout=saved==='true'}catch(e){}
const layoutButton=document.createElement('button');layoutButton.id='layout-toggle';layoutButton.className='quiet';
$('devices').before(layoutButton);
function applyLayout(){document.body.classList.toggle('tv-layout',tvLayout);layoutButton.textContent=tvLayout?'TV layout: On':'TV layout: Off';layoutButton.setAttribute('aria-pressed',String(tvLayout))}
layoutButton.onclick=()=>{tvLayout=!tvLayout;try{localStorage.setItem('movie-time-tv-layout',String(tvLayout))}catch(e){}applyLayout()};
applyLayout();
let movies=[],selected=null,mode='all',limit=42,lastStatus=null,sourceIndex=0,returnFocus=null,hideTimer=null,lastSave=0,refreshing=false;
const video=$('video');
// Custom timeline avoids Android WebView's native range-control D-pad handling.
let timelineValue=0,pendingSeek=null,playRequested=false,playAttempt=0,playbackChanging=false;
Object.defineProperty($('seek'),'value',{get:()=>timelineValue,set:value=>{timelineValue=Math.max(0,Math.min(1000,Number(value)||0));$('seek').style.setProperty('--seek-progress',(timelineValue/10)+'%');$('seek').setAttribute('aria-valuenow',String(Math.round(timelineValue)))}});
$('seek').value=0;
function previewSeek(seconds){if(!Number.isFinite(video.duration)||video.duration<=0)return;pendingSeek=Math.max(0,Math.min(video.duration-0.1,(pendingSeek===null?video.currentTime:pendingSeek)+seconds));$('seek').value=1000*pendingSeek/video.duration;$('time').textContent=clock(pendingSeek)+' / '+clock(video.duration);$('player-status').textContent='Press OK to play from here';showControls()}
function commitSeek(){const target=pendingSeek===null?video.currentTime:pendingSeek;pendingSeek=null;if(!Number.isFinite(target))return;video.currentTime=target;$('player-status').textContent='Loading selected position…';requestPlayback().catch(()=>{$('player-status').textContent='Could not resume. Go Back and reopen this movie to retry.'});showControls()}
$('seek').onclick=e=>{if(e.detail===0){commitSeek();return}const bounds=$('seek').getBoundingClientRect();if(Number.isFinite(video.duration)&&video.duration>0&&bounds.width){pendingSeek=Math.max(0,Math.min(video.duration-0.1,Math.max(0,Math.min(1,(e.clientX-bounds.left)/bounds.width))*video.duration));$('seek').value=1000*pendingSeek/video.duration;commitSeek();}$('seek').focus();showControls()};

let history={};try{history=JSON.parse(localStorage.getItem('movie-time-progress')||'{}')}catch(e){}
async function api(url,options){const r=await fetch(url,options);if(!r.ok){let t=await r.text();try{t=JSON.parse(t).error||t}catch(e){}throw Error(t||'Request failed')}return r.json()}
function jsonPost(url,data){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
function progressKey(){return selected.id+':'+sourceIndex}
function savedFor(movie){return Object.values(history).filter(p=>p.id===movie.id&&p.time>15&&p.duration-p.time>20).sort((a,b)=>b.updated-a.updated)[0]}
function saveProgress(){if(playbackChanging||!selected||!Number.isFinite(video.duration)||!video.currentTime)return;history[progressKey()]={id:selected.id,source:sourceIndex,time:video.currentTime,duration:video.duration,updated:Date.now()};try{localStorage.setItem('movie-time-progress',JSON.stringify(history))}catch(e){}}
function tags(movie,field){const raw=movie[field]||'';if(field==='language'){const names=['Hindi','English','Tamil','Telugu','Malayalam','Kannada','Marathi','Bengali','Punjabi','Urdu','Japanese','Chinese','Korean','Russian','Indonesian','Polish'];const found=names.filter(name=>new RegExp('\\b'+name+'\\b','i').test(raw));if(/Panjabi/i.test(raw)&&!found.includes('Punjabi'))found.push('Punjabi');return found.length?found:(raw?['Other']:[])}return raw.split(',').map(s=>s.trim()==='Science Fiction'?'Sci-Fi':s.trim()).filter(Boolean)}
function filterOptions(id,field){const old=$(id).value;$(id).length=1;Array.from(new Set(movies.flatMap(m=>tags(m,field)))).sort().forEach(v=>$(id).add(new Option(v,v)));$(id).value=old;}
function render(){
 const query=$('search').value.toLowerCase().trim(),language=$('language').value,genre=$('genre').value;
 let found=movies.filter(m=>(!query||[m.title,m.year,m.language,m.genre].join(' ').toLowerCase().includes(query))&&(!language||tags(m,'language').includes(language))&&(!genre||tags(m,'genre').includes(genre))&&(mode==='all'?m.kind!=='episode':mode==='shows'?(m.kind==='series'||(m.kind==='episode'&&!m.series_id)):savedFor(m)));
 if(mode==='shows')found.sort((a,b)=>(a.series||a.title).localeCompare(b.series||b.title)||(a.season||0)-(b.season||0)||(a.episode||0)-(b.episode||0));
 if(mode==='continue')found.sort((a,b)=>savedFor(b).updated-savedFor(a).updated);
 $('heading').firstChild.textContent=mode==='all'?'All movies ':mode==='shows'?'TV Shows ':'Continue watching ';
 $('count').textContent=found.length+' titles';
 const active=document.activeElement&&document.activeElement.dataset.movie;
 $('grid').replaceChildren();
 found.slice(0,limit).forEach(m=>{const card=document.createElement('button');card.className='card';card.dataset.movie=m.id;card.setAttribute('aria-label',m.title+' '+m.year);const wrap=document.createElement('div');wrap.className='poster-wrap';const img=document.createElement('img');img.loading='lazy';img.src='/poster/'+m.id;img.alt=m.title;img.onerror=()=>{img.removeAttribute('src');img.alt='Poster unavailable'};wrap.append(img);if(m.quality){const badge=document.createElement('span');badge.className='badge';badge.textContent=m.quality;wrap.append(badge)}const saved=savedFor(m);if(saved){const p=document.createElement('div');p.className='progress';p.style.width=Math.min(100,100*saved.time/saved.duration)+'%';wrap.append(p)}const title=document.createElement('h3');title.textContent=m.title;const meta=document.createElement('p');meta.textContent=[m.episode_count?m.episode_count+' episodes':m.year,m.language].filter(Boolean).join(' · ');card.append(wrap,title,meta);card.onclick=()=>openMovie(m,card);$('grid').append(card)});
 $('empty').hidden=found.length>0;$('empty').textContent=movies.length===0?(lastStatus&&lastStatus.running?'Importing your channel. Movies will appear here as they are found.':'No movie posts found yet. Try Refresh channel.'):(mode==='continue'?'Movies you start watching will appear here.':'No movies match these filters.');$('more').hidden=found.length<=limit;
 if(active){const card=Array.from($('grid').children).find(c=>c.dataset.movie===active);if(card)card.focus()}
}
async function loadMovies(){const data=await api('/api/movies');movies=data.movies;filterOptions('language','language');filterOptions('genre','genre');render()}
async function poll(){if(refreshing)return;refreshing=true;try{const s=await api('/api/status'),old=lastStatus;lastStatus=s;$('pair').hidden=s.paired;$('library').hidden=!s.paired;$('devices').hidden=!s.paired;$('connection').textContent=!s.paired?'Enter your laptop pairing code to continue.':s.error|| (s.running?'Importing channel · '+s.scanned+' posts scanned · '+s.count+' titles found':s.count+' titles in your library · Connected to your laptop');$('refresh').disabled=!!s.running;if(s.paired&&(!old||!old.paired||old.count!==s.count||old.running!==s.running))await loadMovies();}catch(e){$('connection').textContent='Laptop connection lost. Keep the launcher open, then reload this page.'}finally{refreshing=false}}
$('pair-form').onsubmit=async e=>{e.preventDefault();try{await jsonPost('/api/pair',{pin:$('pin').value.trim()});$('pair-error').textContent='';lastStatus=null;await poll();$('browse').focus()}catch(err){$('pair-error').textContent=err.message}};
function setMode(next){mode=next;limit=42;$('home').classList.toggle('active',mode==='all');$('continued').classList.toggle('active',mode==='continue');$('shows').classList.toggle('active',mode==='shows');$('language').value='';$('genre').value='';render();$('grid').scrollIntoView({block:'start'})}
$('shows').onclick=()=>setMode('shows');$('home').onclick=()=>setMode('all');$('continued').onclick=()=>setMode('continue');
['search','language','genre'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',()=>{limit=42;render()}));
$('browse').onclick=()=>{$('search').scrollIntoView({block:'center'});$('search').focus()};
$('more').onclick=()=>{const old=limit;limit+=42;render();if($('grid').children[old])$('grid').children[old].focus()};
$('refresh').onclick=async()=>{try{await jsonPost('/api/sync',{});await poll()}catch(e){$('connection').textContent=e.message}};
function openMovie(movie,card){selected=movie;returnFocus=card;const saved=savedFor(movie);sourceIndex=saved?saved.source:0;$('detail-title').textContent=movie.title;$('detail-poster').src='/poster/'+movie.id;$('detail-poster').alt=movie.title;$('metadata').textContent=[movie.year,movie.language,movie.genre].filter(Boolean).join(' · ');$('synopsis').textContent=movie.synopsis||'Choose a version below to start watching.';$('file-info').textContent=[movie.quality,movie.size,movie.subtitle?'Subtitles: '+movie.subtitle:''].filter(Boolean).join(' · ');$('versions').replaceChildren();movie.versions.forEach((v,i)=>$('versions').add(new Option(v,i)));$('versions').value=sourceIndex;$('version-caption').textContent=movie.kind==='series'?'Choose an episode':'Choose a version';$('versions-label').hidden=movie.versions.length<2;updateResume();$('detail').hidden=false;$('play').focus();}
function updateResume(){const p=history[progressKey()];const resumable=p&&p.time>15&&p.duration-p.time>20;$('play').textContent=resumable?'▶ Resume at '+clock(p.time):selected.kind==='series'?'▶ Play episode':'▶ Play movie';$('restart').hidden=!resumable;}
$('versions').onchange=()=>{sourceIndex=Number($('versions').value);updateResume()};
function closeDetail(){$('detail').hidden=true;render();const card=Array.from($('grid').children).find(c=>selected&&c.dataset.movie===String(selected.id));(card||$('search')).focus();}
$('close-detail').onclick=closeDetail;
async function playMovie(restart=false){playbackChanging=true;updateNextEpisode();pendingSeek=null;$('player').hidden=false;$('playing-title').textContent=selected.kind==='series'?selected.versions[sourceIndex]:selected.title;$('player-status').textContent='Opening movie…';$('toggle').focus();video.src='/stream/'+selected.id+'?source='+sourceIndex;const p=history[progressKey()];video.onloadedmetadata=()=>{playbackChanging=false;if(!restart&&p&&p.duration-p.time>20)video.currentTime=Math.min(p.time,video.duration-1)};try{await requestPlayback()}catch(e){$('player-status').textContent='Could not start playback. Press Play to retry.'}showControls();}
function hasNextEpisode(){return selected&&selected.kind==='series'&&sourceIndex+1<selected.versions.length}
function updateNextEpisode(){$('next-episode').hidden=!hasNextEpisode()}
$('next-episode').onclick=()=>{if(!hasNextEpisode()||playbackChanging)return;saveProgress();pausePlayback();playbackChanging=true;sourceIndex++;$('versions').value=String(sourceIndex);updateResume();playMovie(true)};
$('play').onclick=()=>playMovie();$('restart').onclick=()=>playMovie(true);
function closePlayer(){pendingSeek=null;saveProgress();pausePlayback();video.removeAttribute('src');video.load();$('player').hidden=true;clearTimeout(hideTimer);if(document.fullscreenElement&&document.exitFullscreen)document.exitFullscreen().catch(()=>{});updateResume();$('play').focus();}
$('close-player').onclick=closePlayer;
function setBuffering(active){$('buffering').hidden=!active;}
function updatePlayIcon(){$('toggle').classList.toggle('is-playing',playRequested);$('toggle').setAttribute('aria-label',playRequested?'Pause':'Play')}
async function requestPlayback(){const attempt=++playAttempt;playRequested=true;updatePlayIcon();setBuffering(true);try{await video.play()}catch(error){if(attempt!==playAttempt)return;playRequested=false;setBuffering(false);updatePlayIcon();throw error}}
function pausePlayback(){++playAttempt;playRequested=false;video.pause();setBuffering(false);updatePlayIcon()}
function toggle(){if(pendingSeek!==null){commitSeek();return}if(!playRequested)requestPlayback().catch(()=>{$('player-status').textContent='Playback failed. Try another version.'});else pausePlayback();showControls()}
$('toggle').onclick=toggle;
function seek(seconds){if(Number.isFinite(video.duration))video.currentTime=Math.max(0,Math.min(video.duration,video.currentTime+seconds));showControls()}
$('rewind').onclick=()=>seek(-10);$('forward').onclick=()=>seek(10);

$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else if($('player').requestFullscreen)$('player').requestFullscreen().catch(()=>{});};
function clock(seconds){if(!Number.isFinite(seconds))return '0:00';seconds=Math.floor(seconds);const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=String(seconds%60).padStart(2,'0');return h?h+':'+String(m).padStart(2,'0')+':'+s:m+':'+s}
video.ontimeupdate=()=>{$('time').textContent=clock(pendingSeek===null?video.currentTime:pendingSeek)+' / '+clock(video.duration);if(pendingSeek===null)$('seek').value=Number.isFinite(video.duration)?1000*video.currentTime/video.duration:0;if(Date.now()-lastSave>4000){lastSave=Date.now();saveProgress()}};
video.onplay=()=>{playRequested=true;updatePlayIcon();if(video.readyState<3)setBuffering(true)};
video.onplaying=()=>{playRequested=true;setBuffering(false);$('player-status').textContent='';updatePlayIcon();showControls()};
video.onpause=()=>{playRequested=false;setBuffering(false);updatePlayIcon();saveProgress();showControls()};
video.onwaiting=()=>{setBuffering(playRequested);updatePlayIcon();if(playRequested)$('player-status').textContent='Buffering…';showControls()};
video.onseeking=()=>{setBuffering(playRequested);updatePlayIcon()};
video.onseeked=()=>{if(video.readyState>=3)setBuffering(false)};
video.onended=()=>{playRequested=false;setBuffering(false);updatePlayIcon();saveProgress();$('player-status').textContent='Movie finished';showControls()};
video.onerror=async()=>{playRequested=false;setBuffering(false);updatePlayIcon();if(!video.getAttribute('src'))return;$('player-status').textContent='This video could not play. Checking the file…';try{const r=await fetch(video.getAttribute('src'),{method:'HEAD'});$('player-status').textContent=r.ok?'This device may not support this video or audio format. Try another version.':r.status===503?'Telegram connection interrupted. Wait a moment, then reopen the movie.':'Movie unavailable ('+r.status+'). Check access to the backup channel.'}catch(e){$('player-status').textContent='Laptop connection lost. Check that the launcher is running.'}showControls()};
function showControls(){$('player').classList.remove('controls-hidden');clearTimeout(hideTimer);if(!video.paused&&pendingSeek===null)hideTimer=setTimeout(()=>$('player').classList.add('controls-hidden'),4500)}
$('player').onmousemove=showControls;$('player').ontouchstart=showControls;video.onclick=toggle;window.addEventListener('pagehide',saveProgress);
$('devices').onclick=()=>{const s=lastStatus||{};$('device-instructions').textContent=s.local?'Use one of these laptop addresses in the TV app:':'Find your laptop address and pairing code in its Movie Time launcher.';$('device-addresses').replaceChildren();(s.addresses||[]).forEach(address=>{const p=document.createElement('div');p.textContent=address;$('device-addresses').append(p)});$('device-pin').textContent=s.pin?'Pairing code: '+s.pin:'';$('device-dialog').hidden=false;$('close-devices').focus()};
$('close-devices').onclick=()=>{$('device-dialog').hidden=true;$('devices').focus()};
function back(){if(!$('player').hidden){closePlayer();return true}if(!$('detail').hidden){closeDetail();return true}if(!$('device-dialog').hidden){$('close-devices').click();return true}return false}
window.movieTimeBack=back;
// Spatial navigation keeps remote focus inside the active screen.
document.addEventListener('keydown',e=>{
 const remoteKeys={13:'Enter',23:'Enter',66:'Enter',19:'ArrowUp',20:'ArrowDown',21:'ArrowLeft',22:'ArrowRight',37:'ArrowLeft',38:'ArrowUp',39:'ArrowRight',40:'ArrowDown'};
 const key=e.key&&e.key!=='Unidentified'?e.key:remoteKeys[e.keyCode];
 if(['Escape','BrowserBack'].includes(key)){if(back())e.preventDefault();return}
 if(!$('player').hidden&&document.activeElement===$('seek')&&['Enter','Accept','Select',' '].includes(key)){e.preventDefault();e.stopPropagation();if(!e.repeat)commitSeek();return}
 if(!$('player').hidden){showControls();if(key==='MediaPlayPause'||key===' '){e.preventDefault();toggle();return}if(key==='MediaRewind'){seek(-10);return}if(key==='MediaFastForward'){seek(10);return}}
 if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(key))return;
 const active=document.activeElement;
 // The player has explicit rows; geometric navigation can skip the wide timeline.
 if(!$('player').hidden){
  e.preventDefault();e.stopPropagation();
  const id=active&&active.id;
  const row=['rewind','toggle','forward','next-episode','fullscreen'].filter(name=>$(name).getClientRects().length);
  let target=null;
  if(id==='close-player'){
   if(key==='ArrowDown')target='seek';
  }else if(id==='seek'){
   if(key==='ArrowUp')target='close-player';
   else if(key==='ArrowDown')target='toggle';
   else previewSeek(key==='ArrowLeft'?-10:10);
  }else if(row.includes(id)){
   if(key==='ArrowUp')target='seek';
   else if(key==='ArrowLeft'||key==='ArrowRight')target=row[Math.max(0,Math.min(row.length-1,row.indexOf(id)+(key==='ArrowLeft'?-1:1)))];
  }else target='toggle';
  if(target)$(target).focus();
  return;
 }
 if(active&&['INPUT','SELECT'].includes(active.tagName)){
  if(active.tagName==='SELECT'||active.type==='range'||['ArrowLeft','ArrowRight'].includes(key))return;
 }
 const scope=!$('player').hidden?$('player'):!$('detail').hidden?$('detail'):!$('device-dialog').hidden?$('device-dialog'):!$('pair').hidden?$('pair'):document.body;
 const nodes=Array.from(scope.querySelectorAll('button,a,input,select')).filter(n=>!n.disabled&&n.getClientRects().length);
 if(!nodes.includes(active)){if(nodes[0])nodes[0].focus();e.preventDefault();return}
 const r=active.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;let best=null,score=Infinity;
 for(const n of nodes){if(n===active)continue;const b=n.getBoundingClientRect(),dx=b.left+b.width/2-x,dy=b.top+b.height/2-y,h=key==='ArrowLeft'||key==='ArrowRight',forward=key==='ArrowLeft'?-dx:key==='ArrowRight'?dx:key==='ArrowUp'?-dy:dy,cross=h?Math.abs(dy):Math.abs(dx);if(forward>4){const s=forward+cross*3;if(s<score){score=s;best=n}}}
 if(best){best.focus();best.scrollIntoView({block:'nearest',inline:'nearest'})}e.preventDefault();
},true);
poll();setInterval(poll,4000);
