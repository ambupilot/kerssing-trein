(() => {
  const form = document.getElementById("logout-form");
  if (!form) return;
  form.addEventListener("submit", async event => {
    if (form.dataset.eiCleared === "1") return;
    event.preventDefault();
    if (!confirm("Uitloggen verwijdert ook lokale EI-concepten op dit apparaat, inclusief nog niet gesynchroniseerde gegevens. Doorgaan?")) return;
    try {
      if ("serviceWorker" in navigator) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        for (const registration of registrations) {
          if (registration.active?.scriptURL.endsWith("/ei-sw.js")) await registration.unregister();
        }
      }
      const keys = await caches.keys();
      await Promise.all(keys.filter(key => key.startsWith("kerssing-ei-")).map(key => caches.delete(key)));
      await new Promise((resolve,reject) => {
        const req=indexedDB.deleteDatabase("kerssing-ei");
        req.onsuccess=resolve;req.onerror=()=>reject(req.error);
        req.onblocked=()=>reject(Error("Sluit andere EI-tabbladen voordat je uitlogt."));
      });
    } catch (error) { alert("Lokale EI-gegevens konden niet veilig worden verwijderd: "+error.message); return; }
    form.dataset.eiCleared="1";
    form.requestSubmit();
  });
})();