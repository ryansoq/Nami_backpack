const http = require('http');
const { WebSocketServer } = require('ws');
const fs = require('fs');

const { execFile } = require('child_process');

const PORT = 18805;
const FRAME_PATH = '/tmp/nami-eye-latest.jpg';
const FRAME_DIR = '/tmp/nami-eye-frames';

// Ensure frame directory exists
if (!fs.existsSync(FRAME_DIR)) fs.mkdirSync(FRAME_DIR, { recursive: true });

let latestFrameBase64 = null;
let latestFrameBuffer = null;
let sessionFrameCount = 0;
let sessionStartTime = null;

// ── HTML Pages ──

const cameraHTML = `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>Nami Eye - Camera</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#111;color:#eee;font-family:system-ui;display:flex;flex-direction:column;align-items:center;height:100vh;overflow:hidden}
video{width:100%;max-width:640px;border-radius:8px;margin-top:12px}
canvas{display:none}
.status{padding:8px 16px;font-size:14px;opacity:.7;margin-top:8px}
.controls{display:flex;gap:12px;margin-top:12px}
button{background:#333;color:#eee;border:none;padding:10px 20px;border-radius:8px;font-size:16px;cursor:pointer}
button:active{background:#555}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.dot.on{background:#4f4}
.dot.off{background:#f44}
.caption{width:100%;max-width:640px;min-height:48px;margin-top:8px;padding:12px 16px;background:rgba(0,206,209,0.15);border:1px solid rgba(0,206,209,0.3);border-radius:8px;font-size:15px;line-height:1.5;text-align:center;display:none;animation:fadeIn 0.3s}
.caption.show{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
</style>
</head><body>
<video id="v" autoplay playsinline muted></video>
<canvas id="c" width="640" height="480"></canvas>
<div class="controls">
  <button id="recBtn" style="background:#c33;padding:12px 28px;font-size:18px;border-radius:50px">⏺ Start</button>
  <button id="switchBtn">🔄</button>
  <span style="font-size:14px;line-height:40px">⏱ <span id="iv">2</span>s</span>
  <input type="range" id="fps" min="1" max="5" value="2" style="width:100px">
</div>
<div class="caption" id="caption">✨</div>
<div class="status">
  <span class="dot off" id="dot"></span>
  <span id="st">Disconnected</span> · Frames: <span id="fc">0</span> · <span id="dur"></span>
</div>
<script>
const v=document.getElementById('v'),c=document.getElementById('c'),ctx=c.getContext('2d');
const dot=document.getElementById('dot'),st=document.getElementById('st'),fc=document.getElementById('fc');
let facing='environment',stream=null,ws=null,count=0,lastData='';
let audioStream=null,mediaRec=null,audioChunks=[];

async function startCam(){
  if(stream) stream.getTracks().forEach(t=>t.stop());
  try{
    stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:facing,width:{ideal:640},height:{ideal:480}},audio:false});
    v.srcObject=stream;
  }catch(e){st.textContent='Camera error: '+e.message}
}

async function startMic(){
  try{
    audioStream=await navigator.mediaDevices.getUserMedia({audio:true});
  }catch(e){console.log('No mic:',e)}
}

function startAudioRec(){
  if(!audioStream) return;
  audioChunks=[];
  mediaRec=new MediaRecorder(audioStream,{mimeType:'audio/webm;codecs=opus'});
  mediaRec.ondataavailable=e=>{if(e.data.size>0) audioChunks.push(e.data)};
  mediaRec.start();
}

function stopAndSendAudio(){
  return new Promise(resolve=>{
    if(!mediaRec||mediaRec.state==='inactive'){resolve(null);return}
    mediaRec.onstop=async()=>{
      if(audioChunks.length===0){resolve(null);return}
      const blob=new Blob(audioChunks,{type:'audio/webm'});
      const buf=await blob.arrayBuffer();
      const b64=btoa(String.fromCharCode(...new Uint8Array(buf)));
      audioChunks=[];
      resolve(b64);
    };
    mediaRec.stop();
  });
}

const cap=document.getElementById('caption');
function connect(){
  const proto=location.protocol==='https:'?'wss:':'ws:';
  ws=new WebSocket(proto+'//'+location.host+'/ws?role=camera');
  ws.onopen=()=>{dot.className='dot on';st.textContent='Connected'};
  ws.onclose=()=>{dot.className='dot off';st.textContent='Disconnected';setTimeout(connect,2000)};
  ws.onerror=()=>ws.close();
  ws.onmessage=e=>{
    try{const d=JSON.parse(e.data);if(d.caption){cap.textContent='✨ '+d.caption;cap.className='caption show'}}catch(x){}
  };
}

async function capture(){
  if(!ws||ws.readyState!==1||!stream) return;
  ctx.drawImage(v,0,0,640,480);
  const data=c.toDataURL('image/jpeg',0.5);
  const b64=data.split(',')[1];
  if(!b64||b64===lastData) return;
  // Send frame + any speech text
  const speech=pendingSpeech; pendingSpeech='';
  ws.send(JSON.stringify({frame:b64,speech:speech||null}));
  lastData=b64;
  count++;fc.textContent=count;
}

let interval=2000,timer=null,recording=false,startTime=0,pendingSpeech='';

// Web Speech API for real-time STT
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let recognition=null;
if(SR){
  recognition=new SR();
  recognition.lang='zh-TW';
  recognition.continuous=true;
  recognition.interimResults=false;
  recognition.onresult=e=>{
    for(let i=e.resultIndex;i<e.results.length;i++){
      if(e.results[i].isFinal){
        const txt=e.results[i][0].transcript.trim();
        if(txt){pendingSpeech+=(pendingSpeech?' ':'')+txt;console.log('🎤',txt)}
      }
    }
  };
  recognition.onerror=e=>console.log('SR error:',e.error);
  recognition.onend=()=>{if(recording)recognition.start()};
}
const recBtn=document.getElementById('recBtn'),dur=document.getElementById('dur');

function startCapture(){clearInterval(timer);timer=setInterval(capture,interval)}
function stopCapture(){clearInterval(timer);timer=null}

function updateDur(){
  if(!recording) return;
  const s=Math.floor((Date.now()-startTime)/1000);
  const m=Math.floor(s/60),ss=s%60;
  dur.textContent=String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0');
  requestAnimationFrame(updateDur);
}

recBtn.onclick=async()=>{
  recording=!recording;
  if(recording){
    await fetch('/api/start',{method:'POST'});
    recBtn.textContent='⏹ Stop';
    recBtn.style.background='#333';
    startTime=Date.now();
    count=0;fc.textContent='0';
    pendingSpeech='';
    updateDur();
    startCapture();
    if(recognition) try{recognition.start()}catch(e){}
  }else{
    stopCapture();
    if(recognition) try{recognition.stop()}catch(e){}
    const r=await fetch('/api/stop',{method:'POST'}).then(r=>r.json());
    recBtn.textContent='⏺ Start';
    recBtn.style.background='#c33';
    dur.textContent='⏹ '+r.frames+' frames / '+r.duration+'s';
  }
};

document.getElementById('switchBtn').onclick=()=>{facing=facing==='environment'?'user':'environment';startCam()};
document.getElementById('fps').oninput=e=>{interval=e.target.value*1000;document.getElementById('iv').textContent=e.target.value;if(recording)startCapture()};
startCam();connect();
</script>
</body></html>`;

const viewerHTML = `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nami Eye - Viewer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#111;color:#eee;font-family:system-ui;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh}
img{max-width:100%;max-height:85vh;border-radius:8px}
.ts{padding:8px;font-size:13px;opacity:.6;margin-top:8px}
.none{font-size:18px;opacity:.4}
</style>
</head><body>
<img id="img" style="display:none">
<div class="none" id="none">Waiting for camera...</div>
<div class="ts" id="ts"></div>
<script>
const img=document.getElementById('img'),none=document.getElementById('none'),ts=document.getElementById('ts');
const proto=location.protocol==='https:'?'wss:':'ws:';
const ws=new WebSocket(proto+'//'+location.host+'/ws?role=viewer');
ws.onmessage=e=>{
  img.src='data:image/jpeg;base64,'+e.data;
  img.style.display='block';none.style.display='none';
  ts.textContent='Last frame: '+new Date().toLocaleTimeString();
};
ws.onclose=()=>{ts.textContent='Disconnected';setTimeout(()=>location.reload(),3000)};
</script>
</body></html>`;

// ── Server ──

const server = http.createServer((req, res) => {
  if (req.url === '/' || req.url === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(cameraHTML);
  } else if (req.url === '/view') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(viewerHTML);
  } else if (req.url === '/api/latest') {
    if (latestFrameBuffer) {
      res.writeHead(200, { 'Content-Type': 'image/jpeg', 'Cache-Control': 'no-cache' });
      res.end(latestFrameBuffer);
    } else {
      res.writeHead(404); res.end('No frame yet');
    }
  } else if (req.url === '/api/latest-base64') {
    if (latestFrameBase64) {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end(latestFrameBase64);
    } else {
      res.writeHead(404); res.end('No frame yet');
    }
  } else if (req.url === '/api/start' && req.method === 'POST') {
    // Clear old session files (frames, speech, audio)
    const files = fs.readdirSync(FRAME_DIR);
    files.forEach(f => fs.unlinkSync(FRAME_DIR + '/' + f));
    sessionFrameCount = 0;
    sessionStartTime = Date.now();
    // Wake OpenClaw immediately so she can watch in real-time
    const hookToken = (() => { try { return JSON.parse(fs.readFileSync('/home/ymchang/.openclaw/openclaw.json','utf8')).hooks.token; } catch(e) { return ''; } })();
    if (hookToken) {
      const msg = '👁️ [Nami Eye] Recording started! Analyze frames in real-time at /tmp/nami-eye-latest.jpg and /tmp/nami-eye-frames/. Send captions back via POST /api/caption. When done, the user will press Stop.';
      const postData = JSON.stringify({ text: msg, mode: 'now' });
      execFile('curl', ['-s', '-X', 'POST', 'http://127.0.0.1:18789/hooks/wake',
        '-H', 'Authorization: Bearer ' + hookToken,
        '-H', 'Content-Type: application/json',
        '-d', postData], (err, stdout) => {
        if (err) console.error('Wake failed:', err);
        else console.log('Wake OK (start):', stdout);
      });
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
  } else if (req.url === '/api/stop' && req.method === 'POST') {
    const duration = sessionStartTime ? Math.floor((Date.now() - sessionStartTime) / 1000) : 0;
    sessionStartTime = null;
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, frames: sessionFrameCount, duration }));
  } else if (req.url === '/api/caption' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const { text } = JSON.parse(body);
        const msg = JSON.stringify({ caption: text });
        for (const c of cameras) {
          if (c.readyState === 1) c.send(msg);
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      } catch(e) {
        res.writeHead(400); res.end('Bad JSON');
      }
    });
  } else {
    res.writeHead(404); res.end('Not found');
  }
});

const wss = new WebSocketServer({ server, path: '/ws' });
const viewers = new Set();
const cameras = new Set();

wss.on('connection', (ws, req) => {
  const role = new URL(req.url, 'http://x').searchParams.get('role');

  if (role === 'viewer') {
    viewers.add(ws);
    ws.on('close', () => viewers.delete(ws));
    // Send latest frame immediately if available
    if (latestFrameBase64) ws.send(latestFrameBase64);
  } else if (role === 'camera') {
    cameras.add(ws);
    ws.on('close', () => cameras.delete(ws));
    ws.on('message', (data) => {
      const raw = data.toString();
      let b64, speech = null;
      try {
        const msg = JSON.parse(raw);
        b64 = msg.frame;
        speech = msg.speech || null;
      } catch(e) {
        b64 = raw; // backward compat: plain base64 frame
      }
      latestFrameBase64 = b64;
      latestFrameBuffer = Buffer.from(b64, 'base64');
      // Save frame to disk
      fs.writeFile(FRAME_PATH, latestFrameBuffer, () => {});
      if (sessionStartTime) {
        sessionFrameCount++;
        const num = String(sessionFrameCount).padStart(5, '0');
        fs.writeFile(FRAME_DIR + '/frame_' + num + '.jpg', latestFrameBuffer, () => {});
        // Save speech text if present
        if (speech) {
          fs.writeFile(FRAME_DIR + '/speech_' + num + '.txt', speech, () => {});
          console.log('🎤 Frame ' + num + ': ' + speech);
        }
      }
      // Broadcast frame to viewers
      for (const v of viewers) {
        if (v.readyState === 1) v.send(b64);
      }
    });
  }
});

server.listen(PORT, () => {
  console.log(`👁️ Nami Eye running on port ${PORT}`);
  console.log(`   Camera: http://localhost:${PORT}/`);
  console.log(`   Viewer: http://localhost:${PORT}/view`);
});
