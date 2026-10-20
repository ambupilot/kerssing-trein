const CACHE="kerssing-ei-v1";
const STATIC=["/static/ei.js","/static/ei-schema.json","/static/style.css","/static/app.js"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE).then(async cache=>{await cache.addAll(STATIC);await self.skipWaiting();}));});
self.addEventListener("activate",event=>{event.waitUntil((async()=>{for(const key of await caches.keys())if(key.startsWith("kerssing-ei-")&&key!==CACHE)await caches.delete(key);await self.clients.claim();})());});
self.addEventListener("message",event=>{if(event.data?.type==="CLEAR_EI_CACHE")event.waitUntil(caches.delete(CACHE));});
self.addEventListener("fetch",event=>{
const request=event.request,url=new URL(request.url);
if(request.method!=="GET"||url.origin!==self.location.origin)return;
if(url.pathname==="/ei/new"){
event.respondWith((async()=>{try{const response=await fetch(request);if(response.ok&&response.headers.get("content-type")?.includes("text/html")){const cache=await caches.open(CACHE);await cache.put(request,response.clone());}return response;}catch(e){return (await caches.match(request))||Response.error();}})());return;
}
if(STATIC.includes(url.pathname)){
event.respondWith((async()=>{const cached=await caches.match(request);if(cached)return cached;return fetch(request);})());
}
});