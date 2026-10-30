const $ = (id) => document.getElementById(id);
let state = null,
  networkLink = "",
  lastSignature = "",
  uploading = false;
const bytes = (n) => {
  if (!n) return "0 B";
  const k = 1024,
    i = Math.min(3, Math.floor(Math.log(n) / Math.log(k)));
  return (
    (n / Math.pow(k, i)).toFixed(i ? 1 : 0) + " " + ["B", "KB", "MB", "GB"][i]
  );
};
function element(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}
function message(text, error = false) {
  $("form-message").textContent = text;
  $("form-message").style.color = error ? "#95442a" : "#496641";
  $("form-message").hidden = false;
}
function toast(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  setTimeout(() => ($("toast").hidden = true), 3000);
}
function tab(which) {
  const link = which === "link";
  $("link-panel").hidden = !link;
  $("upload-panel").hidden = link;
  for (const [id, on] of [
    ["link-tab", link],
    ["upload-tab", !link],
  ]) {
    $(id).setAttribute("aria-selected", String(on));
    $(id).tabIndex = on ? 0 : -1;
  }
}
$("link-tab").onclick = () => tab("link");
$("upload-tab").onclick = () => tab("upload");
for (const id of ["link-tab", "upload-tab"])
  $(id).onkeydown = (e) => {
    if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
      const which = id === "link-tab" ? "upload" : "link";
      tab(which);
      $(which + "-tab").focus();
    }
  };
async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw Error("Unable to connect");
    state = await response.json();
    $("connection").textContent = "Local server online";
    $("save-button").disabled = !state.downloader;
    networkLink = state.links[0] || location.origin;
    $("network-link").textContent = networkLink;
    $("free-space").textContent = bytes(state.free) + " free on this computer";
    if (!state.downloader)
      message(
        "Link saving needs yt-dlp on this computer. Uploads are ready to use.",
        true,
      );
    render();
  } catch (error) {
    $("connection").textContent = "Reconnecting…";
    $("save-button").disabled = true;
  }
}
function render() {
  if (!state) return;
  const query = $("search").value.trim().toLowerCase();
  const signature = JSON.stringify([state.jobs, query]);
  if (lastSignature === signature) return;
  lastSignature = signature;
  const complete = state.jobs.filter((j) => j.status === "complete");
  const shown = complete.filter((j) => j.title.toLowerCase().includes(query));
  $("video-count").textContent = complete.length;
  $("empty").hidden =
    complete.length > 0 ||
    state.jobs.some((j) =>
      ["queued", "downloading", "uploading"].includes(j.status),
    );
  $("videos").replaceChildren();
  $("jobs").replaceChildren();
  const newestComplete = Math.max(0, ...complete.map((job) => job.created));
  let failedHistory = null;
  function appendJob(box, job) {
    if (job.status === "failed" && job.created < newestComplete) {
      if (!failedHistory) {
        failedHistory = element("details", "failed-history");
        const count = state.jobs.filter(
          (item) => item.status === "failed" && item.created < newestComplete,
        ).length;
        failedHistory.append(
          element("summary", "", count + " earlier unsuccessful attempt" + (count === 1 ? "" : "s")),
        );
        $("jobs").append(failedHistory);
      }
      failedHistory.append(box);
    } else {
      $("jobs").append(box);
    }
  }
  for (const job of state.jobs
    .filter((j) => j.status !== "complete")
    .slice(0, 20)) {
    const box = element("div", "job " + job.status);
    const top = element("div", "job-top");
    top.append(
      element("strong", "", job.title),
      element(
        "small",
        "",
        job.status === "failed"
          ? "Could not save"
          : job.status === "queued"
            ? "Queued"
            : Math.round(job.progress) + "%",
      ),
    );
    box.append(
      top,
      element(
        "p",
        "",
        job.detail ||
          (job.status === "queued"
            ? "Waiting for a free download slot…"
            : "Receiving video…"),
      ),
    );
    if (job.status !== "failed") {
      const bar = element("div", "progress");
      bar.setAttribute("role", "progressbar");
      bar.setAttribute("aria-label", job.title);
      bar.setAttribute("aria-valuenow", Math.round(job.progress));
      bar.setAttribute("aria-valuemin", "0");
      bar.setAttribute("aria-valuemax", "100");
      const fill = element("div");
      fill.style.width = Math.max(3, Math.min(100, job.progress)) + "%";
      bar.append(fill);
      box.append(bar);
    }
    appendJob(box, job);
  }
  for (const job of shown) {
    const card = element("article", "video-card");
    const art = element("div", "video-art");
    const play = element("button", "play-round", "▶");
    play.setAttribute("aria-label", "Play " + job.title);
    play.onclick = () => openPlayer(job);
    art.append(
      play,
      element("span", "format-badge", job.file.split(".").pop().toUpperCase()),
    );
    const body = element("div", "video-body");
    const title = element("h3", "video-title", job.title);
    title.title = job.title;
    const meta = element(
      "p",
      "video-meta",
      bytes(job.size) +
        " · " +
        new Date(job.created * 1000).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        }),
    );
    const actions = element("div", "video-actions");
    const watch = element("button", "watch-button", "▶ Watch");
    watch.onclick = () => openPlayer(job);
    const download = element("a", "download-button", "↓ Download");
    download.href = job.download_url;
    download.download = "";
    actions.append(watch, download);
    body.append(title, meta, actions);
    card.append(art, body);
    $("videos").append(card);
  }
  if (query && !shown.length)
    $("videos").append(
      element("p", "video-meta", "No videos match your search."),
    );
}
$("search").oninput = render;
function openPlayer(job) {
  $("player-title").textContent = job.title;
  $("player").src = job.url;
  $("player-dialog").showModal();
  $("player")
    .play()
    .catch(() => {});
}
function closePlayer() {
  $("player-dialog").close();
  $("player").pause();
  $("player").removeAttribute("src");
  $("player").load();
}
$("close-player").onclick = closePlayer;
$("player-dialog").addEventListener("cancel", (e) => {
  e.preventDefault();
  closePlayer();
});
$("link-form").onsubmit = async (event) => {
  event.preventDefault();
  if (!state) return;
  $("save-button").disabled = true;
  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-App-Key": state.csrf },
      body: JSON.stringify({
        url: $("video-url").value,
        quality: $("quality").value,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error);
    $("video-url").value = "";
    message("Added to the queue. You can keep adding videos.");
    await refresh();
  } catch (error) {
    message(error.message, true);
  } finally {
    $("save-button").disabled = !state?.downloader;
  }
};
$("copy-link").onclick = async () => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(networkLink);
    } else {
      const input = element("textarea");
      input.value = networkLink;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.append(input);
      input.select();
      const ok = document.execCommand("copy");
      input.remove();
      if (!ok) throw Error("Copy unavailable");
    }
    toast("Network link copied");
  } catch {
    $("network-link").textContent = networkLink;
    toast("Network link: " + networkLink);
  }
};
function uploadFile(file, index, total) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.setRequestHeader("X-App-Key", state.csrf);
    xhr.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        $("upload-status").textContent =
          `Uploading ${index} of ${total}: ${file.name} · ${Math.round((e.loaded / e.total) * 100)}%`;
    };
    xhr.onload = () => {
      let result;
      try {
        result = JSON.parse(xhr.responseText);
      } catch {
        reject(Error("Upload failed. Please reconnect and try again."));
        return;
      }
      xhr.status < 300 ? resolve(result) : reject(Error(result.error));
    };
    xhr.onerror = () =>
      reject(Error("Upload interrupted. Check your connection and try again."));
    xhr.send(file);
  });
}
async function uploadFiles(files) {
  if (uploading || !files.length) return;
  if (!state) {
    message("Wait for the server connection and try again.", true);
    return;
  }
  uploading = true;
  $("file-input").disabled = true;
  let saved = 0;
  const failures = [];
  try {
    for (const [i, file] of [...files].entries()) {
      try {
        if (file.size > state.max_size)
          throw Error(file.name + ": Maximum file size is 8 GB.");
        await uploadFile(file, i + 1, files.length);
        saved++;
        await refresh();
      } catch (error) {
        failures.push(error.message);
      }
    }
    $("upload-status").textContent = saved
      ? `${saved} video${saved === 1 ? "" : "s"} added to your library.`
      : "No videos uploaded.";
    if (failures.length) message(failures.join(" "), true);
    else toast("Upload complete");
  } finally {
    uploading = false;
    $("file-input").disabled = false;
    $("file-input").value = "";
    await refresh();
  }
}
$("file-input").onchange = (e) => uploadFiles(e.target.files);
for (const event of ["dragenter", "dragover"])
  $("drop-zone").addEventListener(event, (e) => {
    e.preventDefault();
    $("drop-zone").classList.add("dragging");
  });
for (const event of ["dragleave", "drop"])
  $("drop-zone").addEventListener(event, (e) => {
    e.preventDefault();
    $("drop-zone").classList.remove("dragging");
  });
$("drop-zone").addEventListener("drop", (e) =>
  uploadFiles(e.dataTransfer.files),
);
refresh();
setInterval(refresh, 2000);
