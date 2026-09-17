/* The parent page. Plain fetches against /api/parent/*, with an optional PIN
   sent as a header. Nothing here is child-facing. */
(function () {
  "use strict";
  var pin = "";
  try { pin = sessionStorage.getItem("parent-pin") || ""; } catch (e) {}
  var $ = function (id) { return document.getElementById(id); };

  // True only while the requests that follow somebody actually typing the PIN
  // into the gate box are in flight. The server forgives wrong-PIN tries on a
  // *typed* PIN and not on the header this page sends by itself afterwards -
  // it polls every thirty seconds with nobody at the keyboard, and each of
  // those polls used to hand back the guesses the sums overlay was counting on
  // the child's own device. See `_forgive()` in app/main.py.
  var typed = false;

  function api(url, opts) {
    opts = opts || {};
    var extra = pin ? { "X-Parent-Pin": pin } : {};
    if (typed && pin) extra["X-Parent-Pin-Typed"] = "1";
    opts.headers = Object.assign({}, opts.headers || {}, extra);
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) { needPin(); throw new Error("pin"); }
      return r.json().then(function (d) { if (!r.ok) throw new Error(d.detail || "failed"); return d; });
    });
  }

  function needPin() {
    $("pin").hidden = false;
    $("body").hidden = true;
    $("pin-input").focus();
  }
  $("pin-go").addEventListener("click", function () {
    pin = $("pin-input").value;
    try { sessionStorage.setItem("parent-pin", pin); } catch (e) {}
    $("pin-bad").hidden = true;
    // The whole of `load()` is one deliberate entry, so the flag covers the
    // burst it fires rather than a single request - and comes off as soon as
    // that burst is done, whichever way it went.
    typed = true;
    load()
      .catch(function () { $("pin-bad").hidden = false; })
      .then(function () { typed = false; }, function () { typed = false; });
  });
  $("pin-input").addEventListener("keydown", function (e) { if (e.key === "Enter") $("pin-go").click(); });

  // Tap a thumbnail to see it full size - a 150px square is not enough to
  // judge whether the screen was right.
  var lightbox = $("lightbox"), lbImg = lightbox.querySelector("img"),
      lbVid = lightbox.querySelector("video"), lbAud = lightbox.querySelector("audio"),
      lbInfo = $("lb-info");
  // `item` is optional: a gallery item to describe under the picture. Today's
  // grid is pictures only, so this is where "what did they ask for" lives now.
  // `media` is "image" | "video" | "audio". A song is both: the drawn waveform
  // in the <img> and the file in the <audio> under it, which is why this takes
  // a poster as well as the file.
  function showBig(src, media, item, poster) {
    // Historically this took a boolean "isVideo"; a few callers still do.
    if (media === true) media = "video";
    else if (media === false || !media) media = "image";
    lbVid.hidden = media !== "video";
    lbAud.hidden = media !== "audio";
    lbImg.hidden = media === "video";
    if (media === "video") { lbVid.src = src; lbAud.removeAttribute("src"); }
    else if (media === "audio") { lbAud.src = src; lbImg.src = poster || ""; lbVid.removeAttribute("src"); }
    else { lbImg.src = src; lbVid.removeAttribute("src"); lbAud.removeAttribute("src"); }
    lbInfo.innerHTML = "";
    lbInfo.hidden = !item;
    if (item) {
      var kind = { image: "Picture", panel: "Comic picture", comic: "Comic", t2v: "Video", i2v: "Video from a picture",
                   upload: "Photo or drawing", movie: "Film joined from clips", voice: "Video with a voice over it", sound: "Video with a sound",
                   sticker: "Sticker", frame: "Picture from a video", music: "Song",
                   smooth: "Video made smooth", slowmo: "Video in slow motion",
                   huge: "Picture made four times bigger", loop: "Moving sticker" }[item.kind] || (item.media === "video" ? "Video" : "Picture");
      lbInfo.innerHTML =
        "<b>" + esc(kind) + " · " + esc(when(item.created)) + (item.favourite ? " · ⭐ favourite" : "") +
        (item.name ? " · “" + esc(item.name) + "”" : "") + "</b>" +
        "<div>" + (item.idea ? esc(item.idea) : "<span class='muted'>(no words - a photo or drawing)</span>") + "</div>" +
        (item.prompt && item.prompt !== item.idea ? "<div class='prompt'>Full prompt: " + esc(item.prompt) + "</div>" : "") +
        // What a song actually sings. The prompt only says what it should
        // sound like, which is not the half a parent wants to read.
        (item.lyrics && item.lyrics.trim() && item.lyrics.trim() !== "[inst]"
          ? "<div class='prompt'>The words:</div><pre class='lyric-sheet'>" +
            esc(item.lyrics.trim()) + "</pre>"
          : item.media === "audio" ? "<div class='muted small'>Music only - nobody sings on this one.</div>" : "") +
        (item.tags && item.tags.length ? "<div class='muted small'>Tags: " + item.tags.map(esc).join(", ") + "</div>" : "");
      var row = document.createElement("div"); row.className = "row";
      var bin = document.createElement("button"); bin.className = "danger"; bin.textContent = "Move to the trash";
      bin.addEventListener("click", function (e) {
        e.stopPropagation();
        api("/api/gallery/" + encodeURIComponent(item.id), { method: "DELETE" })
          .then(function () { closeBig(); load(); }).catch(function () {});
      });
      row.appendChild(bin);
      lbInfo.appendChild(row);
    }
    lightbox.hidden = false;
  }
  function closeBig() {
    lightbox.hidden = true; lbVid.pause(); lbVid.removeAttribute("src"); lbImg.removeAttribute("src");
  }
  // Close on a tap *outside* the content: the info panel has a button in it.
  lightbox.addEventListener("click", function (e) {
    if (!e.target.closest(".lb-info")) closeBig();
  });

  function esc(t) {
    var d = document.createElement("span");
    d.textContent = t == null ? "" : t;
    return d.innerHTML;
  }

  function when(ts) {
    var d = new Date(ts * 1000);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function bytes(n) {
    if (!n) return "0 KB";
    if (n >= 1e9) return (n / 1e9).toFixed(1) + " GB";
    if (n >= 1e6) return Math.round(n / 1e6) + " MB";
    return Math.max(1, Math.round(n / 1e3)) + " KB";
  }

  // A glance at the day: pictures only. A forty-word prompt under each tile
  // made the strip a wall of text; the words are one tap away in the modal.
  function renderToday(items) {
    var box = $("today-strip");
    box.innerHTML = items.length ? "" : '<p class="muted">Nothing made today yet.</p>';
    items.slice().reverse().forEach(function (i) {
      var tile = document.createElement("button");
      tile.type = "button";
      tile.className = "thumb";
      tile.title = i.idea || "";
      var img = document.createElement("img");
      img.loading = "lazy";
      img.alt = i.idea || "";
      img.src = "/api/gallery/" + encodeURIComponent(i.id) + "/thumb?v=" + i.version;
      tile.appendChild(img);
      // A ▶ for a video and a ♪ for a song: the thumbnail of a waveform is
      // recognisable, but not at 90px in a row of pictures.
      var glyph = i.media === "video" ? "\u25B6" : i.media === "audio" ? "\u266A" : "";
      if (glyph) { var m = document.createElement("span"); m.className = "mark"; m.textContent = glyph; tile.appendChild(m); }
      if (i.favourite) { var st = document.createElement("span"); st.className = "mark star"; st.textContent = "\u2B50"; tile.appendChild(st); }
      // Whose it is, but only once that is a question. With one child every
      // tile would carry the same name and it would mean nothing.
      if (people.length > 1) {
        // No `who` on the file means it predates profiles, and the server
        // gives those to whichever profile adopts - so this does the same.
        var adopter = people.filter(function (w) { return w.adopts; })[0] || {};
        var owner = i.who || adopter.id;
        var maker = people.filter(function (w) { return w.id === owner; })[0];
        var tag = document.createElement("span");
        tag.className = "mark whose-mark";
        tag.textContent = maker ? maker.emoji : "?";
        tag.title = maker ? maker.name : "nobody in particular";
        tile.appendChild(tag);
      }
      tile.addEventListener("click", function () {
        showBig("/api/gallery/" + encodeURIComponent(i.id) + "/file?v=" + i.version, i.media, i,
                "/api/gallery/" + encodeURIComponent(i.id) + "/poster?v=" + i.version);
      });
      box.appendChild(tile);
    });
  }

  // The zip endpoint takes ids and is not PIN-gated, so a plain <a download>
  // streams it - no holding a few hundred megabytes in a blob to do it.
  function renderDownloads(s) {
    // ?what= rather than every id in the URL: a few hundred ids is longer
    // than nginx will accept in a request line.
    function wire(id, what, count, label) {
      var a = $(id);
      if (!count) {
        a.setAttribute("aria-disabled", "true");
        a.removeAttribute("href");
        a.textContent = label + " (none)";
        return;
      }
      a.removeAttribute("aria-disabled");
      a.href = "/api/gallery/zip?what=" + what;
      a.textContent = label + " (" + count + ")";
    }
    wire("zip-today", "today", (s.today_items || []).length, "Today");
    wire("zip-favs", "favourites", (s.favourites || []).length, "Favourites");
    wire("zip-all", "all", (s.all_ids || []).length, "Everything");
  }

  function renderSpace(space) {
    var used = space.total || 0;
    var parts = [["vid", space.videos || 0], ["pic", space.pictures || 0], ["bin", space.trash || 0]];
    parts.forEach(function (p) {
      var el = document.querySelector(".spacebar ." + p[0]);
      el.style.width = used ? (p[1] / used * 100).toFixed(1) + "%" : "0";
    });
    // Only the parts that exist: "0 KB of pictures" is noise, not information.
    var legend = [
      ["var(--accent-i2v)", space.videos, "of videos"],
      ["var(--accent-image)", space.pictures, "of pictures"],
      ["var(--card-edge)", space.trash, "in the trash"],
    ].filter(function (p) { return p[1]; }).map(function (p) {
      return '<span class="swatch" style="background:' + p[0] + '"></span>' + bytes(p[1]) + " " + p[2];
    });
    $("space-legend").innerHTML = (legend.length ? legend.join(" &nbsp; ") : "Nothing saved yet") +
      (space.free ? " &mdash; " + bytes(space.free) + " still free on the disk." : ".");
  }

  function render(s) {
    $("pin").hidden = true;
    $("body").hidden = false;
    var t = s.today;
    $("today").innerHTML = [
      ["Pictures", t.image], ["Videos", t.videos], ["Songs", t.music],
      ["Uploads", t.upload], ["Films", t.movie]
    ].map(function (p) { return '<div class="tile-stat"><b>' + p[1] + '</b><span>' + p[0] + ' today</span></div>'; }).join("");
    $("totals").textContent = s.total_items + (s.total_items === 1 ? " thing" : " things") +
      " in the gallery, " + s.disk_mb + " MB on disk, " + s.trash_count + " in the trash" +
      (s.busy ? ". Making a " + s.busy.kind + " right now (" + Math.round(s.busy.progress * 100) + "%)." : ".");

    // Who there is, before the tiles: renderToday marks each with its maker
    // and reads `people` to do it. The other way round, the first paint had
    // no marks and they appeared on the next poll thirty seconds later.
    paintWhose(s);
    renderToday(s.today_items || []);
    renderDownloads(s);
    renderSpace(s.space || {});

    $("paused").checked = !!s.settings.paused;
    paintHours(s);
    paintCloseOn(s);
    paintModules(s.modules || []);

    paintSums(s);

    put("limit", s.settings.daily_video_limit || 0);
    put("image-limit", s.settings.daily_image_limit || 0);
    put("music-limit", s.settings.daily_music_limit || 0);
    // No music model on this machine means no songs to limit.
    $("music-limit-row").hidden = !s.music;
    $("bonus-music").hidden = !s.music;

    // Spell out what the limits mean right now, so "3" in a box is not the
    // only thing to go on.
    var a = s.allowance || {};
    var lines = [];
    ["image", "video", "music"].forEach(function (kind) {
      var k = a[kind];
      if (!k || !k.limit) return;
      var thing = kind === "image" ? "picture" : kind === "music" ? "song" : "video";
      lines.push(thing.charAt(0).toUpperCase() + thing.slice(1) + "s: <b>" + k.left +
        " left</b> today — " + k.used + " of " + (k.limit + k.bonus) + " used" +
        (k.bonus ? " (" + k.limit + " a day plus " + k.bonus + " extra)" : "") + ".");
    });
    $("left-today").innerHTML = lines.length ? lines.join("<br>") : "";
    $("bonus-row").hidden = !((a.image && a.image.limit) || (a.video && a.video.limit) ||
                             (a.music && a.music.limit));
    // Only offer to take a top-up back when there is one to take back.
    var given = (a.image && a.image.bonus || 0) + (a.video && a.video.bonus || 0) +
                (a.music && a.music.bonus || 0);
    $("clear-bonus").hidden = given === 0;
    bonusGiven = a;

    var n = s.notify || {};
    ["made", "attach", "limit", "digest", "flagged", "pin"].forEach(function (k) {
      $("n-" + k).checked = !!n[k];
      $("n-" + k).disabled = !n.configured;
    });
    $("n-attach").disabled = !n.configured || !n.made;
    // The PIN alert is the one that also goes by email, so it stays usable
    // for a household with a mail relay and no bot - and Save with it.
    var anyChannel = n.configured || (s.digest && s.digest.configured);
    $("n-pin").disabled = !anyChannel;
    $("notify-save").disabled = !anyChannel;
    $("notify-test").disabled = !n.configured;
    $("notify-state").innerHTML = n.configured
      ? (n.count === 1 ? "Sending to <b>" + esc(n.targets[0]) + "</b>. "
                       : "Sending to <b>" + n.count + " places</b>. ") +
        "Files over " + n.max_mb + " MB are mentioned rather than attached."
      : "<span class='bad'>Nothing set up yet</span> — put one or more URLs in " +
        "the box below.";
    paintSecret("notify_urls", n.urls);
    put("n-maxmb", n.max_mb);
    $("n-maxmb").disabled = !n.configured;
    paintRoutes(n);

    // Asking it back. Hidden entirely unless there is a Telegram bot with a
    // chat id to allow - with no allowlist there is no safe way to accept a
    // message, so there is nothing to offer.
    var t = s.telegram || {};
    // Shown as soon as there is a bot token, not only once somebody is allowed
    // to use it: with no allowlist the bot can talk and not listen, and the box
    // that fixes that is on this card.
    $("ask-card").hidden = !t.has_token;
    $("n-ask").checked = !!t.enabled;
    $("n-ask").disabled = !t.possible;
    $("ask-state").innerHTML = !t.possible
      ? "<span class='bad'>Nobody may ask it yet</span> — it can send messages, " +
        "but with no chat ID it has no safe way to accept one. Put one below."
      : t.enabled
        ? "On. Answering with <b>" + esc(t.model) + "</b>, for " + t.allowed +
          (t.allowed === 1 ? " chat ID." : " chat IDs.")
        : "Off — the bot only talks, it does not listen.";
    paintSecret("telegram_token", t.token);
    put("t-chatids", t.chat_ids || "");
    put("t-timeout", t.timeout || 120);
    $("t-chatids").placeholder = t.from_url || "123456789, 987654321";

    var d = s.digest || {};
    put("digest-on", !!d.enabled);
    put("digest-at", d.at || "19:30");
    put("limit-mail", !!d.limit_mail);
    put("digest-max", d.max_items || 24);
    $("digest-config").innerHTML = d.configured
      ? "Goes to <b>" + d.to.map(esc).join(", ") + "</b> from " + esc(d.from_name) +
        " &lt;" + esc(d.from) + "&gt; via " + esc(d.smtp) + "." +
        (d.last_sent ? " Last sent " + esc(d.last_sent) + "." : " Not sent yet.")
      : "<span class='bad'>Not set up yet</span> — fill in the email server below.";
    paintMailServer(d);

    paintSettings(s);
    paintDeployment(s.deployment);
    paintPin(s);
    paintNaming(s);
    paintBackups(s.backups || []);

    $("refused-count").textContent = s.refused.length ? "(" + s.refused.length + ")" : "";
    $("refused").innerHTML = s.refused.length ? "" : '<p class="muted">Nothing refused.</p>';
    s.refused.forEach(function (r) {
      var box = document.createElement("div");
      box.className = "refused-item";
      var img = document.createElement("img");
      // the image needs the PIN header too, so fetch it as a blob
      fetch("/api/parent/refused/" + encodeURIComponent(r.id), { headers: pin ? { "X-Parent-Pin": pin } : {} })
        .then(function (x) { return x.blob(); }).then(function (b) { img.src = URL.createObjectURL(b); });
      img.addEventListener("click", function () { if (img.src) showBig(img.src, false); });
      box.appendChild(img);
      var small = document.createElement("small"); small.textContent = when(r.when); box.appendChild(small);
      var row = document.createElement("div"); row.className = "row";
      var allow = document.createElement("button"); allow.className = "primary"; allow.textContent = "Allow";
      allow.addEventListener("click", function () {
        api("/api/parent/refused/" + encodeURIComponent(r.id) + "/allow", { method: "POST" }).then(load);
      });
      var drop = document.createElement("button"); drop.className = "danger"; drop.textContent = "Remove";
      drop.addEventListener("click", function () {
        api("/api/parent/refused/" + encodeURIComponent(r.id), { method: "DELETE" }).then(load);
      });
      row.appendChild(allow); row.appendChild(drop); box.appendChild(row);
      $("refused").appendChild(box);
    });

    var trash = s.trash || [];
    $("trash-count").textContent = trash.length ? "(" + trash.length + ")" : "";
    $("empty-trash").hidden = trash.length === 0;
    // An empty trash should say *why* it is empty. "Nothing was deleted" and
    // "it was emptied an hour ago" look identical otherwise, and the second
    // one is what a parent is actually asking about.
    var emptied = s.settings.trash_emptied_at || 0;
    var why = "The trash is empty.";
    if (!trash.length && emptied) {
      why = "The trash is empty \u2014 last emptied " + when(emptied) + " by " +
        esc(s.settings.trash_emptied_by || "someone") + " (" +
        (s.settings.trash_emptied_count || 0) + " thing" +
        ((s.settings.trash_emptied_count || 0) === 1 ? "" : "s") + " gone for good).";
    } else if (!trash.length) {
      why = "The trash is empty. Anything deleted turns up here for " +
        (s.trash_days || 7) + " days.";
    }
    $("trash").innerHTML = trash.length ? "" : '<p class="muted">' + why + "</p>";
    trash.forEach(function (t) {
      var box = document.createElement("div");
      box.className = "refused-item";
      var url = "/api/gallery/trash/" + encodeURIComponent(t.id) + "/file?v=" + t.version;
      var poster = "/api/gallery/trash/" + encodeURIComponent(t.id) + "/poster?v=" + t.version;
      var media;
      if (t.media === "video") {
        media = document.createElement("video");
        media.muted = true; media.playsInline = true; media.preload = "metadata";
        media.src = url + "#t=0.1";
      } else {
        // A song is its drawn waveform, not the mp3 - an <img> pointing at an
        // mp3 is a broken-image icon, which is what this row was.
        media = document.createElement("img");
        media.src = t.media === "audio" ? poster : url;
      }
      media.addEventListener("click", function () { showBig(url, t.media, null, poster); });
      box.appendChild(media);
      var small = document.createElement("small");
      small.textContent = (t.idea ? t.idea.slice(0, 40) + " · " : "") + "deleted " + when(t.deleted_at) +
        " · gone in " + Math.max(0, Math.round((t.purge_at - Date.now() / 1000) / 86400)) + "d";
      box.appendChild(small);
      var row = document.createElement("div"); row.className = "row";
      var back = document.createElement("button"); back.className = "primary"; back.textContent = "Put back";
      back.addEventListener("click", function () {
        api("/api/gallery/trash/" + encodeURIComponent(t.id) + "/restore", { method: "POST" }).then(load);
      });
      var gone = document.createElement("button"); gone.className = "danger"; gone.textContent = "Delete now";
      gone.addEventListener("click", function () {
        api("/api/gallery/trash/" + encodeURIComponent(t.id), { method: "DELETE" }).then(load);
      });
      row.appendChild(back); row.appendChild(gone); box.appendChild(row);
      $("trash").appendChild(box);
    });

    var o = s.ollama || {}, lr = s.ollama_last_run;

    // One line that answers "is it working?". Everything a number could tell
    // you is still there, folded into Details.
    var verdict = $("verdict"), state = "good", says = "Everything's working.";
    if (!s.comfy_reachable) {
      state = "bad"; says = "The picture maker is offline — nothing can be made right now.";
    } else if (s.settings.paused) {
      state = s.settings.closed_reason ? "bad" : "warn";
      says = s.settings.closed_reason
        ? "The factory closed itself: " + s.settings.closed_reason + "."
        : "The factory is closed. The sign says \u201cback soon\u201d.";
    } else if (s.schedule && s.schedule.on && !s.schedule.open && !s.schedule.opens_day) {
      // A timetable that is on with nothing in it. Amber, because that is a
      // mistake rather than the timetable working - and without this branch
      // the one below threw on the missing day and froze the whole panel.
      state = "warn";
      says = "Closed \u2014 the timetable is on but has no open times in it. " +
        "Add some below, or untick it.";
    } else if (s.schedule && s.schedule.on && !s.schedule.open) {
      // Not a warning: this is the timetable working. Saying it in the same
      // amber as a real problem would train a parent to ignore the line.
      state = "good";
      says = "Closed for now \u2014 that's the timetable. " +
        (s.schedule.opens_day === "today"
          ? "It opens again at " + clockish(s.schedule.opens) + "."
          : "It opens again " + (s.schedule.opens_day === "tomorrow" ||
             s.schedule.opens_day.indexOf("next ") === 0 ? s.schedule.opens_day :
             "on " + s.schedule.opens_day) + " at " + clockish(s.schedule.opens) + ".");
    } else if (!o.reachable) {
      state = "warn"; says = "Working, but the idea helper is offline — \u201cSurprise me\u201d and the script writer won't answer.";
    } else if (s.busy) {
      says = "Working. A " + (s.busy.kind === "image" ? "picture" : "video") +
        " is being made right now (" + Math.round(s.busy.progress * 100) + "%).";
    }
    verdict.className = "verdict " + state;
    verdict.textContent = says;

    $("system").innerHTML =
      "ComfyUI: <span class='" + (s.comfy_reachable ? "ok'>reachable" : "bad'>not reachable") + "</span><br>" +
      "Ollama: <span class='" + (o.reachable ? "ok'>reachable" : "bad'>not reachable") + "</span>" +
      (o.loaded && o.loaded.length ? " — loaded: " + o.loaded.map(function (m) { return m.name + (m.fully_on_gpu ? " (GPU)" : " (CPU!)"); }).join(", ") : " — nothing loaded (good: VRAM is free)") + "<br>" +
      (lr ? "Last helper run: " + lr.tokens_per_sec + " tok/s, " + (lr.looked_gpu_accelerated ? "<span class='ok'>on the GPU</span>" : "<span class='bad'>looked CPU-bound</span>") + ", model " + lr.model : "The helper has not run yet.") +
      (s.pin_required ? "<br>PIN protection is on." : "<br>No PIN set (Settings → The PIN on this page adds one).");
  }

  // Which makers exist. Two different states to show, and they want different
  // sentences: a parent turned this off, or this machine cannot do it.
  function paintModules(list) {
    var box = $("modules");
    if (!box) return;
    box.innerHTML = list.map(function (m) {
      var id = "mod-" + m.id;
      return "<div class='module" + (m.ready ? "" : " cannot") + "'>" +
        "<label class='toggle'><input type='checkbox' id='" + id + "'" +
        (m.enabled ? " checked" : "") + (m.ready ? "" : " disabled") + "> " +
        esc(m.emoji + " " + m.label) + "</label>" +
        "<span class='what'>" + esc(m.note) + "</span>" +
        (m.ready ? "" : "<span class='cannot-why'>This machine hasn't got the " +
          "model for it, so it is hidden whatever this says.</span>") +
      "</div>";
    }).join("");
  }

  // Whatever paintModules drew, rather than a list written out again here.
  // The list was five names long and a sixth maker made this route answer 500
  // - the server writes a row for every id in modules.IDS and this sent it
  // five of the six, so the story switch arrived as null.
  function saveModules() {
    var box = $("modules");
    var body = {};
    if (box) {
      Array.prototype.forEach.call(box.querySelectorAll("input[type=checkbox]"),
        function (tick) { body[tick.id.replace(/^mod-/, "")] = tick.checked ? 1 : 0; });
    }
    api(scoped("/api/parent/modules"), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function () {
      $("modules-saved").hidden = false;
      setTimeout(function () { $("modules-saved").hidden = true; }, 1500);
      load();
    }).catch(function () {});
  }
  $("modules-save").addEventListener("click", saveModules);

  // What a refusal does next, and - if one has already happened - why the
  // factory they are looking at is shut.
  // --- the sums -------------------------------------------------------------
  // Like the timetable grid, this stops repainting once it has been touched:
  // the page reloads itself every thirty seconds, and a tick springing back
  // while somebody is halfway through choosing four of them is worse than a
  // number in a box going stale for a moment.

  var sumsDirty = false;

  function opBoxes() {
    return Array.prototype.slice.call($("quiz-ops").querySelectorAll("input"));
  }

  function paintSums(s) {
    var q = s.quiz || {};

    // Always: what happened today and what can be done about it. Read-only,
    // so it is outside the guard.
    $("quiz-reset").hidden = !(q.enabled && q.passed_today);
    $("quiz-skip").hidden = !(q.enabled && !q.passed_today);
    $("quiz-state").textContent = !q.enabled ? ""
      : q.bypassed_today ? "You waved " + whoseName() + " through today. The sums come back tomorrow."
      : q.passed_today ? whoseName(true) + " did them at " + q.passed_at + " today."
      : whoseName(true) + " has not done them yet today.";

    if (sumsDirty) return;
    $("quiz-on").checked = !!q.enabled;
    $("quiz-count").value = q.question_count || 3;
    $("quiz-level").value = q.level || "medium";
    var ticked = q.ops || ["add"];
    opBoxes().forEach(function (box) {
      box.checked = ticked.indexOf(box.dataset.op) !== -1;
    });
  }

  function paintCloseOn(s) {
    var select = $("close-on");
    var chosen = s.close_on || "";
    if (!select.options.length) {
      (s.close_choices || []).forEach(function (c) {
        select.appendChild(new Option(c.label, c.id));
      });
    }
    select.value = chosen;

    var why = $("closed-why");
    if (s.settings.paused && s.settings.closed_reason) {
      why.textContent = "It closed itself at " +
        new Date((s.settings.closed_at || 0) * 1000).toLocaleTimeString([], {
          hour: "2-digit", minute: "2-digit" }) +
        ": " + s.settings.closed_reason + ". Unticking the box above opens it " +
        "again and clears this.";
      why.hidden = false;
    } else {
      why.hidden = true;
    }
  }

  // --- when it is open ------------------------------------------------------
  // The page reloads itself every 30 seconds, which is fine for a number in a
  // box and ruinous for seven rows somebody is halfway through editing. So the
  // grid is painted from the server only until it is touched; after that it is
  // the parent's until they Save or reload. The live status line above it is
  // outside that guard - it is read-only and it is the point.

  var hoursDirty = false;
  var DAY_NAMES = [];

  function hhmm(mins) {
    mins = Math.max(0, Math.min(1440, mins | 0));
    return ("0" + Math.floor(mins / 60)).slice(-2) + ":" + ("0" + (mins % 60)).slice(-2);
  }

  function minsOf(text) {
    var bits = String(text || "").split(":");
    var h = parseInt(bits[0], 10), m = parseInt(bits[1], 10) || 0;
    if (isNaN(h)) return null;
    return Math.max(0, Math.min(1440, h * 60 + m));
  }

  function windowRow(from, to) {
    var win = document.createElement("span");
    win.className = "win";
    win.innerHTML = '<input type="time" class="from"> to <input type="time" class="to">' +
      '<button type="button" class="drop" aria-label="Remove this time">\u2715</button>';
    win.querySelector(".from").value = hhmm(from);
    win.querySelector(".to").value = hhmm(to);
    return win;
  }

  function paintHours(s) {
    var st = s.schedule || {};
    DAY_NAMES = s.days || DAY_NAMES;

    // Always: what the timetable adds up to at this moment.
    $("hours-now").textContent = st.on
      ? (st.override ? "Open anyway until midnight \u2014 today's timetable is waived." : st.says)
      : "No timetable \u2014 open whenever it is not closed above.";

    // "Let them in anyway" only exists when there is something to let them past,
    // and turns into its own undo once it is on.
    var anyway = $("hours-anyway");
    if (!st.on || (st.open && !st.override)) {
      anyway.hidden = true;
    } else {
      anyway.hidden = false;
      anyway.textContent = st.override
        ? "Go back to the timetable" : "Let them in anyway until midnight";
      anyway.dataset.on = st.override ? "0" : "1";
    }

    if (hoursDirty) return;
    $("hours-on").checked = !!st.on;

    var grid = $("hours");
    grid.innerHTML = "";
    (DAY_NAMES).forEach(function (day) {
      var windows = (st.week && st.week[day.id]) || [];
      var row = document.createElement("div");
      row.className = "day-row" + (windows.length ? "" : " is-off");
      row.dataset.day = day.id;
      var tick = document.createElement("label");
      tick.className = "toggle";
      tick.innerHTML = '<input type="checkbox" class="day-on"> ' + day.name;
      tick.querySelector("input").checked = windows.length > 0;
      row.appendChild(tick);
      var box = document.createElement("div");
      box.className = "windows";
      (windows.length ? windows : []).forEach(function (w) {
        box.appendChild(windowRow(w[0], w[1]));
      });
      if (!windows.length) {
        var shut = document.createElement("span");
        shut.className = "shut";
        shut.textContent = "shut all day";
        box.appendChild(shut);
      }
      row.appendChild(box);
      var add = document.createElement("button");
      add.type = "button";
      add.className = "add-window";
      add.textContent = "+ another time";
      add.hidden = !windows.length || windows.length >= 4;
      row.appendChild(add);
      grid.appendChild(row);
    });
  }

  // One row of times, read back out of the boxes. A day whose tick is off is
  // written as empty rather than left out, because the server reads a missing
  // day as shut either way and an explicit "mon=" says so out loud.
  function hoursText() {
    return Array.prototype.map.call($("hours").children, function (row) {
      var on = row.querySelector(".day-on").checked;
      var windows = on ? Array.prototype.map.call(
        row.querySelectorAll(".win"), function (win) {
          var a = minsOf(win.querySelector(".from").value);
          var b = minsOf(win.querySelector(".to").value);
          return (a === null || b === null || b <= a) ? null : hhmm(a) + "-" + hhmm(b);
        }).filter(Boolean) : [];
      return row.dataset.day + "=" + windows.join(",");
    }).join(";");
  }

  function touched() { hoursDirty = true; }

  $("hours").addEventListener("input", touched);
  $("hours-on").addEventListener("change", touched);
  $("hours").addEventListener("click", function (ev) {
    var row = ev.target.closest(".day-row");
    if (!row) return;
    if (ev.target.classList.contains("drop")) {
      touched();
      ev.target.closest(".win").remove();
      if (!row.querySelector(".win")) row.querySelector(".day-on").checked = false;
      syncRow(row);
    } else if (ev.target.classList.contains("add-window")) {
      touched();
      // A new window starts where the last one ended, which is nearly always
      // what a second window means: a gap, then more.
      var last = row.querySelector(".win:last-of-type");
      var prevEnd = last ? minsOf(last.querySelector(".to").value) : null;
      var from = prevEnd === null ? 16 * 60 : prevEnd + 60;
      row.querySelector(".windows").appendChild(
        windowRow(Math.min(from, 22 * 60), Math.min(from + 120, 24 * 60)));
      syncRow(row);
    } else if (ev.target.classList.contains("day-on")) {
      touched();
      if (ev.target.checked && !row.querySelector(".win")) {
        row.querySelector(".windows").appendChild(windowRow(16 * 60, 19 * 60));
      }
      syncRow(row);
    }
  });

  function syncRow(row) {
    var count = row.querySelectorAll(".win").length;
    row.classList.toggle("is-off", count === 0);
    row.querySelector(".add-window").hidden = count === 0 || count >= 4;
    var shut = row.querySelector(".shut");
    if (count && shut) shut.remove();
    if (!count && !shut) {
      var span = document.createElement("span");
      span.className = "shut";
      span.textContent = "shut all day";
      row.querySelector(".windows").appendChild(span);
    }
  }

  $("hours-save").addEventListener("click", function () {
    api(scoped("/api/parent/schedule"), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: hoursText(), on: $("hours-on").checked ? 1 : 0 })
    }).then(function () {
      hoursDirty = false;
      $("hours-saved").hidden = false;
      setTimeout(function () { $("hours-saved").hidden = true; }, 1500);
      load();
    }).catch(function () {});
  });

  $("hours-copy").addEventListener("click", function () {
    // Monday to Friday is the shape of nearly every timetable anyone sets, and
    // typing it five times is how a parent decides this feature is not worth it.
    touched();
    var rows = $("hours").children;
    if (rows.length < 5) return;
    var from = rows[0];
    for (var i = 1; i < 5; i++) {
      rows[i].querySelector(".day-on").checked = from.querySelector(".day-on").checked;
      var box = rows[i].querySelector(".windows");
      box.innerHTML = "";
      Array.prototype.forEach.call(from.querySelectorAll(".win"), function (win) {
        box.appendChild(windowRow(minsOf(win.querySelector(".from").value),
                                  minsOf(win.querySelector(".to").value)));
      });
      syncRow(rows[i]);
    }
  });

  $("hours-anyway").addEventListener("click", function () {
    api(scoped("/api/parent/schedule/override"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: $("hours-anyway").dataset.on === "1" })
    }).then(load).catch(function () {});
  });

  // 990 -> "4:30pm". The same wording the closed sign gives them, so a parent
  // reading the verdict and a child reading the overlay see the same time.
  function clockish(mins) {
    if (mins === null || mins === undefined) return "";
    var h = Math.floor(mins / 60), m = mins % 60;
    if (h === 24 || (h === 0 && !m)) return "midnight";
    if (h === 12 && !m) return "midday";
    var show = (h % 12) || 12;
    return show + (m ? ":" + ("0" + m).slice(-2) : "") + (h < 12 ? "am" : "pm");
  }

  // --- whose rules ----------------------------------------------------------
  // Every control in the Rules tab asks the same routes it always did, with
  // ?who= on the end. The server does the rest: a change to a daily limit goes
  // into that child's file and a change to the email goes into the household's,
  // decided by which setting it is rather than by which page sent it.

  var whose = "";
  var people = [];

  function scoped(url) {
    if (!whose) return url;
    return url + (url.indexOf("?") === -1 ? "?" : "&") + "who=" + encodeURIComponent(whose);
  }

  function faceInto(el, who) {
    el.textContent = "";
    el.style.background = who.colour || "#f7b32b";
    if (who.avatar) {
      var img = document.createElement("img");
      img.src = "/api/profiles/" + encodeURIComponent(who.id) + "/avatar?v=" + faceVersion;
      img.alt = "";
      el.appendChild(img);
    } else {
      el.textContent = who.emoji || "\uD83E\uDD8A";
    }
  }
  var faceVersion = Date.now();

  // Whoever the Rules tab is scoped to, by name where there is one. With a
  // single profile that is the only child there is; with several, the bar
  // above says which - so the name is the right word either way, and "your
  // child" is the honest fallback before anybody has been named.
  function whoseName(caps) {
    var chosen = people.filter(function (w) { return w.id === whose; })[0]
      || people[0];
    var name = (chosen && chosen.name) || "";
    return name || (caps ? "Your child" : "your child");
  }

  function paintWhose(s) {
    people = s.who || [];
    whose = s.whose || (people[0] || {}).id || "";
    var many = people.length > 1;
    $("whose-bar").hidden = !many;
    $("whose-note").hidden = !many;
    $("people-card").hidden = false;
    if (many) {
      var chosen = people.filter(function (w) { return w.id === whose; })[0] || people[0];
      $("whose-note").textContent =
        "Open or closed and the filter rule above are for everybody. Everything " +
        "below is " + chosen.name + "'s: their timetable, their makers, their " +
        "sums and their daily limits. People are added and removed on the " +
        "\u201cWho uses it\u201d tab.";
      var box = $("whose-picks");
      box.textContent = "";
      people.forEach(function (who) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "whose-pick" + (who.id === whose ? " is-on" : "");
        var face = document.createElement("span");
        face.className = "whose-face";
        faceInto(face, who);
        var name = document.createElement("span");
        name.textContent = who.name;
        b.appendChild(face);
        b.appendChild(name);
        b.addEventListener("click", function () {
          if (who.id === whose) return;
          whose = who.id;
          // The timetable grid belongs to whoever was showing; a half-edited
          // one must not be carried across to somebody else's week.
          hoursDirty = false;
          load();
        });
        box.appendChild(b);
      });
    }
    paintPeople(s);
  }

  function paintPeople(s) {
    $("shared").checked = !!s.shared;
    var box = $("people");
    box.textContent = "";
    people.forEach(function (who) {
      var row = document.createElement("div");
      row.className = "person";

      var face = document.createElement("span");
      face.className = "whose-face";
      faceInto(face, who);
      row.appendChild(face);

      var name = document.createElement("input");
      name.type = "text";
      name.maxLength = 24;
      name.value = who.name;
      row.appendChild(name);

      var ageLabel = document.createElement("label");
      ageLabel.textContent = "age ";
      var age = document.createElement("input");
      age.type = "number";
      age.min = 0; age.max = 19; age.step = 1;
      age.style.width = "64px";
      age.value = who.age || 0;
      ageLabel.appendChild(age);
      row.appendChild(ageLabel);

      var save = document.createElement("button");
      save.textContent = "Save";
      save.addEventListener("click", function () {
        api("/api/profiles/" + encodeURIComponent(who.id), {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.value, age: parseInt(age.value, 10) || 0 }),
        }).then(function () { badPeople(""); load(); })
          .catch(function (err) { badPeople(err.message); });
      });
      row.appendChild(save);

      if (people.length > 1) {
        var gone = document.createElement("button");
        gone.className = "danger";
        gone.textContent = "Remove";
        // Two taps. Nothing here deletes a picture, but a profile carries a
        // child's rules and their claim on everything they have made, and
        // getting it back means setting all of that up again.
        var sure = false;
        gone.addEventListener("click", function () {
          if (!sure) {
            sure = true;
            gone.textContent = "Really remove " + who.name + "?";
            setTimeout(function () {
              if (!sure) return;
              sure = false;
              gone.textContent = "Remove";
            }, 5000);
            return;
          }
          api("/api/profiles/" + encodeURIComponent(who.id), { method: "DELETE" })
            .then(function () { whose = ""; badPeople(""); load(); })
            .catch(function (err) { badPeople(err.message); });
        });
        row.appendChild(gone);
      } else {
        var only = document.createElement("span");
        only.className = "adopts";
        only.textContent = "the only one here";
        row.appendChild(only);
      }

      // Straight to this person's limits, timetable and makers. Without it,
      // setting up a new child is: add them here, change tab, find them in a
      // row of faces, and only then start.
      var rules = document.createElement("button");
      rules.textContent = "Their rules \u2192";
      rules.addEventListener("click", function () {
        whose = who.id;
        hoursDirty = false;
        showPTab("rules");
        load();
      });
      row.appendChild(rules);
      box.appendChild(row);
    });
  }

  function badPeople(message) {
    $("people-bad").textContent = message || "";
    $("people-bad").hidden = !message;
  }

  $("add-person").addEventListener("click", function () {
    var name = $("new-name").value.trim();
    if (!name) { badPeople("Type a name first."); return; }
    api("/api/profiles", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, age: parseInt($("new-age").value, 10) || 0 }),
    }).then(function (made) {
      $("new-name").value = "";
      $("new-age").value = "";
      badPeople("");
      whose = made.id;
      load();
    }).catch(function (err) { badPeople(err.message); });
  });

  $("shared").addEventListener("change", function () {
    api("/api/profiles/shared", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shared: $("shared").checked }),
    }).then(function () { load(); }).catch(function () {});
  });

  function load() { return api(scoped("/api/parent/summary")).then(render); }

  $("save").addEventListener("click", function () {
    api(scoped("/api/parent/settings"), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paused: $("paused").checked,
        quiz_enabled: $("quiz-on").checked ? 1 : 0,
        quiz_questions: Math.max(1, Math.min(10, parseInt($("quiz-count").value, 10) || 0)) || 0,
        quiz_level: $("quiz-level").value,
        quiz_ops: opBoxes().filter(function (b) { return b.checked; })
          .map(function (b) { return b.dataset.op; }).join(","),
        daily_video_limit: parseInt($("limit").value, 10) || 0,
        daily_image_limit: parseInt($("image-limit").value, 10) || 0,
        daily_music_limit: parseInt($("music-limit").value, 10) || 0,
        close_on: $("close-on").value
      })
    }).then(function () {
      sumsDirty = false;
      clean(["limit", "image-limit", "music-limit"]);
      $("saved").hidden = false;
      setTimeout(function () { $("saved").hidden = true; }, 1500);
      load();
    });
  });
  $("paused").addEventListener("change", function () { $("save").click(); });
  $("close-on").addEventListener("change", function () { $("save").click(); });
  $("quiz-on").addEventListener("change", function () { $("save").click(); });
  $("quiz-count").addEventListener("change", function () { $("save").click(); });
  $("quiz-level").addEventListener("change", function () { $("save").click(); });
  // Somebody is mid-edit from the first keystroke, not from the save.
  ["quiz-on", "quiz-count", "quiz-level", "quiz-ops"].forEach(function (id) {
    $(id).addEventListener("input", function () { sumsDirty = true; });
  });
  $("quiz-ops").addEventListener("change", function (ev) {
    var box = ev.target;
    if (!box.dataset || !box.dataset.op) return;
    // At least one kind has to stay on: with none ticked there are no sums to
    // ask, so the last one springs back rather than being saved and quietly
    // turned into addition by the server.
    if (!opBoxes().some(function (b) { return b.checked; })) {
      box.checked = true;
      $("quiz-ops-msg").hidden = false;
      setTimeout(function () { $("quiz-ops-msg").hidden = true; }, 2500);
      return;
    }
    $("save").click();
  });
  $("quiz-skip").addEventListener("click", function () {
    api(scoped("/api/parent/quiz/bypass"), { method: "POST" }).then(load).catch(function () {});
  });
  $("quiz-reset").addEventListener("click", function () {
    api(scoped("/api/parent/quiz/reset"), { method: "POST" }).then(load).catch(function () {});
  });
  // "Just this once" - a top-up that expires at midnight on its own, so the
  // limit never has to be edited and then remembered about.
  $("digest-save").addEventListener("click", function () {
    api("/api/parent/digest", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: $("digest-on").checked ? 1 : 0,
        at: $("digest-at").value,
        limit_mail: $("limit-mail").checked ? 1 : 0,
        max_items: parseInt($("digest-max").value, 10) || 24
      })
    }).then(function () {
      clean(["digest-at", "digest-max"]);
      $("digest-saved").hidden = false;
      setTimeout(function () { $("digest-saved").hidden = true; }, 1500);
      load();
    }).catch(function (e) { $("digest-result").innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; });
  });

  // The relay itself. Its own section and its own Save: the top of the card
  // is whether the email goes and when, which is a decision somebody makes
  // often, and this is where it goes, which is one they make once.
  function paintMailServer(d) {
    var f = d.fields || {};
    put("d-to", f.digest_to || "");
    put("d-host", f.digest_smtp_host || "");
    put("d-port", f.digest_smtp_port || 25);
    put("d-tls", f.digest_smtp_starttls);
    put("d-user", f.digest_smtp_user || "");
    put("d-from", f.digest_from || "");
    put("d-fromname", f.digest_from_name || "");
    put("d-subject", f.digest_subject || "");
    put("d-limitsubject", f.digest_limit_subject || "");
    $("d-pass-state").innerHTML = d.has_password
      ? "<span class='ok'>One is set.</span>"
      : "None set — fine for a relay that wants none.";
    paintSecret("smtp_pass", d.password);
    // The Apprise URL is a credential too - the shape it is for carries a mail
    // password - so it is a secret box like the one above and never a filled-in
    // field. See app/config.py.
    paintSecret("digest_url", d.url);
    // Leaving these blank is normal and the placeholder says what happens
    // then, so they are filled in from what the server would actually use.
    $("d-fromname").placeholder = d.from_name || "";
    $("d-subject").placeholder = d.subject || "";
  }

  $("server-save").addEventListener("click", function () {
    api("/api/parent/digest", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: $("d-to").value.trim(),
        smtp_host: $("d-host").value.trim(),
        smtp_port: num("d-port", 25),
        smtp_starttls: $("d-tls").checked ? 1 : 0,
        smtp_user: $("d-user").value.trim(),
        sender: $("d-from").value.trim(),
        sender_name: $("d-fromname").value.trim(),
        subject: $("d-subject").value.trim(),
        limit_subject: $("d-limitsubject").value.trim()
      })
    }).then(function () {
      clean(SERVER_IDS);
      $("server-saved").hidden = false;
      setTimeout(function () { $("server-saved").hidden = true; }, 1500);
      $("server-result").textContent = "";
      load();
    }).catch(function (e) {
      $("server-result").innerHTML = "<span class='bad'>" + esc(e.message) + "</span>";
    });
  });

  // Two lines through the relay, and nothing else. "Send a report now" above
  // builds the whole day; the question here is only whether the address works,
  // and an empty day answers that as well as a busy one.
  $("server-test").addEventListener("click", function () {
    var b = $("server-test"), out = $("server-result");
    b.disabled = true;
    out.textContent = "Sending...";
    api("/api/parent/digest/test", { method: "POST" })
      .then(function (r) {
        out.innerHTML = "<span class='ok'>Sent to " +
          esc(r.sent_to.join(", ") || "the Apprise URL") + ".</span>";
      })
      .catch(function (e) { out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; })
      .then(function () { b.disabled = false; });
  });

  // Who may talk to the bot, and how long a question may take. Saved through
  // the alerts route, which is where every other switch on this card goes.
  $("ask-save").addEventListener("click", function () {
    api("/api/parent/notify", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        telegram_chat_ids: $("t-chatids").value.trim(),
        telegram_timeout: num("t-timeout", 120)
      })
    }).then(function () {
      clean(BOT_IDS);
      $("ask-saved").hidden = false;
      setTimeout(function () { $("ask-saved").hidden = true; }, 1500);
      load();
    }).catch(function () {});
  });

  $("digest-test").addEventListener("click", function () {
    var b = $("digest-test"), out = $("digest-result");
    b.disabled = true;
    out.textContent = "Sending...";
    api("/api/parent/digest/send", { method: "POST" })
      .then(function (r) {
        out.innerHTML = "<span class='ok'>Sent to " + esc(r.sent_to.join(", ")) +
          " — " + r.items + " thing" + (r.items === 1 ? "" : "s") + " from today.</span>";
      })
      .catch(function (e) { out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; })
      .then(function () { b.disabled = false; });
  });

  var bonusGiven = {};
  $("clear-bonus").addEventListener("click", function () {
    var jobs = ["image", "video"].filter(function (k) {
      return bonusGiven[k] && bonusGiven[k].bonus;
    }).map(function (k) {
      return api(scoped("/api/parent/bonus"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: k, extra: -bonusGiven[k].bonus })
      });
    });
    Promise.all(jobs).then(load).catch(function () {});
  });

  $("bonus-row").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-bonus]");
    if (!b) return;
    b.disabled = true;
    api(scoped("/api/parent/bonus"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: b.dataset.bonus, extra: parseInt(b.dataset.extra, 10) })
    }).then(load).catch(function () {}).then(function () { b.disabled = false; });
  });

  // Two taps on purpose: "Have a look" says what would go, and only then does
  // the button turn into the one that moves it.
  var tidyArmed = null;
  function tidyBody(preview) {
    return JSON.stringify({
      days: parseInt($("older").value, 10),
      keep_favourites: $("keep-favs").checked,
      preview: preview
    });
  }
  $("tidy").addEventListener("click", function () {
    var b = $("tidy"), out = $("tidy-result");
    if (tidyArmed) {
      clearTimeout(tidyArmed); tidyArmed = null;
      b.disabled = true; out.textContent = "Tidying...";
      api("/api/parent/cleanup", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: tidyBody(false)
      }).then(function (r) {
        out.innerHTML = "<span class='ok'>Moved " + r.moved + " to the trash (" + bytes(r.bytes) + "). Put anything back from there.</span>";
        b.textContent = "Have a look";
        load();
      }).catch(function (e) { out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; })
        .then(function () { b.disabled = false; });
      return;
    }
    b.disabled = true;
    api("/api/parent/cleanup", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: tidyBody(true)
    }).then(function (r) {
      if (!r.count) { out.textContent = "Nothing that old. Nothing to do."; return; }
      out.textContent = "That would move " + r.count + " thing" + (r.count === 1 ? "" : "s") +
        " (" + bytes(r.bytes) + ") to the trash.";
      b.textContent = "Yes, move them";
      tidyArmed = setTimeout(function () {
        tidyArmed = null; b.textContent = "Have a look"; out.textContent = "";
      }, 8000);
    }).catch(function (e) { out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; })
      .then(function () { b.disabled = false; });
  });

  $("empty-trash").addEventListener("click", function () {
    if (!window.confirm("Delete everything in the trash for good?")) return;
    api("/api/parent/trash/empty", { method: "POST" }).then(load);
  });

  // --- the settings that used to live in .env -------------------------------
  // Every one of these is a number or a switch somebody may be halfway through
  // typing when the thirty-second repaint lands, so none of them is painted
  // over once it has been touched. Same rule as the timetable grid above,
  // spelled once here rather than a flag per card: a field is the parent's
  // from the first keystroke until the Save that sends it.

  var dirty = Object.create(null);

  function watch(ids) {
    ids.forEach(function (id) {
      var el = $(id);
      if (!el) return;
      var touch = function () { dirty[id] = true; };
      el.addEventListener("input", touch);
      el.addEventListener("change", touch);
    });
  }


  // --- the deployment values: the parent page over .env ---------------------
  //
  // Four of the eight are credentials and none of those eight values ever
  // comes back from the server: what arrives is {set, source, env, env_set,
  // restart}, which is enough to say where the one in force came from and
  // whether a change needs a restart, and not enough to read a secret off this
  // page. The two widgets below are the whole of it - four secret boxes on
  // Alerts and four plain ones on Settings - so there is one mechanism rather
  // than eight copies of the same fetch.

  // Which of the page and .env is in force, as a sentence.
  function sourceLine(f) {
    if (!f) return "";
    if (f.source === "page")
      return "<span class='ok'>Set here.</span> <code>" + esc(f.env) +
        "</code> in <code>.env</code> " +
        (f.env_set ? "is ignored while this is set." : "is not set.");
    if (f.source === "env")
      return "Not set here — using <code>" + esc(f.env) +
        "</code> from <code>.env</code>.";
    return "<span class='bad'>Not set anywhere.</span>" +
      (f.value ? " Using the built-in <code>" + esc(f.value) + "</code>." : "");
  }

  function restartLine(f) {
    return f && f.restart
      ? "<div class='muted small'>⟳ " + esc(f.restart) + "</div>"
      : "<div class='muted small'>Takes effect straight away — nothing to restart.</div>";
  }

  // One secret box: say whether one is set, take a new one, clear it back to
  // .env. There is no "show it" and no value to show one from.
  function paintSecret(key, f) {
    var box = document.querySelector('.secret[data-key="' + key + '"]');
    if (!box || !f) return;
    box.querySelector("[data-state]").innerHTML = sourceLine(f) + restartLine(f);
    // Clearing means "use .env again", and when .env has nothing that is the
    // same as turning it off. The button says which.
    var clear = box.querySelector("[data-clear]");
    clear.hidden = f.source !== "page";
    clear.textContent = f.env_set ? "Clear (use .env again)" : "Clear";
  }

  function wireSecret(box) {
    var key = box.getAttribute("data-key");
    var input = box.querySelector("[data-input]");
    var error = box.querySelector("[data-error]");
    var saved = box.querySelector("[data-saved]");
    function done() {
      // The box is emptied on success whatever happened: what was typed is a
      // credential and leaving it sitting in the field is the one thing this
      // page must not do.
      input.value = "";
      error.textContent = "";
      saved.hidden = false;
      setTimeout(function () { saved.hidden = true; }, 1500);
      load();
    }
    function failed(e) {
      error.textContent = e.message || "That did not save.";
    }
    box.querySelector("[data-save]").addEventListener("click", function () {
      var value = (input.value || "").trim();
      if (!value) { error.textContent = "Type it in first."; return; }
      api("/api/parent/config", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: key, value: value })
      }).then(done).catch(failed);
    });
    box.querySelector("[data-clear]").addEventListener("click", function () {
      api("/api/parent/config/" + encodeURIComponent(key), { method: "DELETE" })
        .then(done).catch(failed);
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".secret"), wireSecret);

  // The four that are not secrets, drawn from what the server sent rather than
  // written out in the markup - so the labels and the restart notes live in
  // app/config.py, next to the rules about each one.
  var DEPLOY_ROWS = [
    ["comfy_url", "Where the picture maker is", "http://comfyui:8188"],
    ["ollama_url", "Where the helper models are", "http://ollama:11434"],
    ["log_level", "How much the log says",
     "INFO — DEBUG logs every message from the picture maker, and is noisy"],
    ["tz", "The clock “today” is measured against",
     "Europe/Paris, America/Toronto — the household's, not the server's, if they differ"]
  ];

  function paintDeployment(all) {
    var box = $("deploy-rows");
    if (!box || !all) return;
    if (box.dataset.drawn) {
      DEPLOY_ROWS.forEach(function (row) {
        var f = all[row[0]];
        if (!f) return;
        var wrap = box.querySelector('[data-key="' + row[0] + '"]');
        wrap.querySelector("[data-state]").innerHTML = sourceLine(f) + restartLine(f);
        put("dep-" + row[0], f.value || "");
        wrap.querySelector("[data-clear]").hidden = f.source !== "page";
        wrap.querySelector("[data-clear]").textContent =
          f.env_set ? "Clear (use .env again)" : "Clear";
      });
      return;
    }
    box.innerHTML = DEPLOY_ROWS.map(function (row) {
      return '<div class="deploy" data-key="' + row[0] + '">' +
        "<h4>" + esc(row[1]) + "</h4>" +
        '<div class="row">' +
        '<input type="text" id="dep-' + row[0] + '" data-input ' +
        'placeholder="' + esc(row[2]) + '" style="flex:1;min-width:220px">' +
        '<button class="primary" data-save>Save</button>' +
        '<button data-clear hidden>Clear</button>' +
        '<span class="saved" data-saved hidden>Saved</span>' +
        '<span class="bad small" data-error></span>' +
        "</div><p class='muted' data-state></p></div>";
    }).join("");
    box.dataset.drawn = "1";
    Array.prototype.forEach.call(box.querySelectorAll(".deploy"), function (wrap) {
      var key = wrap.getAttribute("data-key");
      var input = wrap.querySelector("[data-input]");
      var error = wrap.querySelector("[data-error]");
      var saved = wrap.querySelector("[data-saved]");
      function done(r) {
        error.textContent = "";
        saved.hidden = false;
        saved.textContent = r && r.restart ? "Saved — restart to apply" : "Saved";
        setTimeout(function () { saved.hidden = true; }, 2500);
        clean(["dep-" + key]);
        load();
      }
      function failed(e) { error.textContent = e.message || "That did not save."; }
      wrap.querySelector("[data-save]").addEventListener("click", function () {
        api("/api/parent/config", {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: key, value: (input.value || "").trim() })
        }).then(done).catch(failed);
      });
      wrap.querySelector("[data-clear]").addEventListener("click", function () {
        api("/api/parent/config/" + encodeURIComponent(key), { method: "DELETE" })
          .then(done).catch(failed);
      });
      input.addEventListener("input", function () { dirty["dep-" + key] = true; });
    });
    paintDeployment(all);
  }

  // The PIN. The current one is typed again rather than taken from the header
  // this page already holds - the same rule grown-up mode uses, and the reason
  // is that a factor nobody entered is not one.
  function paintPin(s) {
    var f = (s.deployment || {}).parent_pin || {};
    $("pin-state").innerHTML = s.pin_required
      ? "<span class='ok'>A PIN is set.</span> " +
        (f.source === "page"
          ? "Changed here. <code>PARENT_PIN</code> in <code>.env</code> " +
            (f.env_set ? "is ignored while this one is set." : "is not set.")
          : "It is <code>PARENT_PIN</code> from <code>.env</code>.")
      : "<span class='bad'>There is no PIN.</span> This page is open to " +
        "anybody who can reach the app, and so is the grown-up box on the sums.";
    $("pin-current").parentNode.hidden = !s.pin_required;
    $("pin-save").textContent = s.pin_required ? "Change it" : "Set a PIN";
  }

  $("pin-save").addEventListener("click", function () {
    var error = $("pin-error");
    var fresh = $("pin-new").value;
    error.textContent = "";
    if (fresh !== $("pin-again").value) {
      error.textContent = "Those two are not the same.";
      return;
    }
    api("/api/parent/pin", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current: $("pin-current").value, new: fresh })
    }).then(function () {
      // The browser is holding the old one and every call after this carries
      // it, so it is swapped here rather than making somebody reload and be
      // asked for a PIN they have just replaced.
      pin = fresh;
      try { sessionStorage.setItem("parent-pin", pin); } catch (e) {}
      ["pin-current", "pin-new", "pin-again"].forEach(function (id) { $(id).value = ""; });
      $("pin-saved").hidden = false;
      setTimeout(function () { $("pin-saved").hidden = true; }, 2000);
      load();
    }).catch(function (e) {
      error.textContent = e.message || "That did not change.";
    });
  });

  function put(id, value) {
    var el = $(id);
    if (!el || dirty[id] || document.activeElement === el) return;
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value;
  }

  function clean(ids) { ids.forEach(function (id) { delete dirty[id]; }); }

  function num(id, fallback) {
    var value = parseFloat($(id).value);
    return isNaN(value) ? fallback : value;
  }

  // One PUT, one "Saved", and the fields it owns stop being the parent's.
  function saveSettings(ids, body, badge) {
    return api(scoped("/api/parent/settings"), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function () {
      clean(ids);
      if (badge && $(badge)) {
        $(badge).hidden = false;
        setTimeout(function () { $(badge).hidden = true; }, 1500);
      }
      load();
    }).catch(function () {});
  }

  var FILTER_IDS = ["screen-uploads", "chat-strict", "music-strict"];
  var LENGTH_IDS = ["vid-min", "vid-max", "vid-def", "vid-sharp",
                    "mus-min", "mus-max", "mus-def"];
  var WORDING_IDS = ["ui-lang", "pronoun", "app-title"];
  var STUFF_IDS = ["trash-days", "max-characters", "sweep-hours"];
  // Its own id and its own Save, because it sits on the backup card rather
  // than with the rest of the tidying-up numbers - it is about the copies on
  // that card, and asking somebody to find it three cards further down would
  // be filing it where the code lives rather than where the question is.
  var BACKUP_IDS = ["backup-keep"];
  var HELD_IDS = ["h-script-keep", "h-chat-keep", "h-free", "h-chat-name",
                  "h-chat-keep-msgs"];
  // The email server, which is its own PUT on its own card.
  var SERVER_IDS = ["d-to", "d-host", "d-port", "d-tls", "d-user", "d-from",
                    "d-fromname", "d-subject", "d-limitsubject"];
  var BOT_IDS = ["t-chatids", "t-timeout"];
  var EXTRA_IDS = ["quiz-bypass", "digest-max", "prompt-editing", "n-maxmb"];
  watch(FILTER_IDS.concat(LENGTH_IDS, WORDING_IDS, STUFF_IDS, BACKUP_IDS, HELD_IDS,
                          SERVER_IDS, BOT_IDS, EXTRA_IDS,
                          ["limit", "image-limit", "music-limit", "digest-at"]));

  function paintSettings(s) {
    var set = s.settings || {};
    put("screen-uploads", set.screen_uploads);
    put("chat-strict", set.chat_strict);
    put("music-strict", set.music_strict);
    put("quiz-bypass", set.quiz_bypass_minutes || 60);
    put("vid-min", set.video_min_seconds);
    put("vid-max", set.video_max_seconds);
    put("vid-def", set.video_default_seconds);
    put("vid-sharp", set.video_max_seconds_sharp);
    put("mus-min", set.music_min_seconds);
    put("mus-max", set.music_max_seconds);
    put("mus-def", set.music_default_seconds);
    put("ui-lang", set.ui_lang || "en");
    put("pronoun", set.kid_pronoun || "they");
    put("app-title", set.app_title || "");
    $("app-title").placeholder = s.default_title || "My AI Factory";
    put("h-script-keep", set.script_keep_alive || "0");
    put("h-chat-keep", set.chat_keep_alive || "5m");
    put("h-free", set.comfy_free_after_job);
    put("h-chat-name", set.chat_name || "Sparky");
    put("h-chat-keep-msgs", set.chat_keep_messages || 400);
    put("trash-days", set.trash_days);
    put("max-characters", set.max_characters);
    put("sweep-hours", set.input_sweep_hours);
    put("backup-keep", set.backup_keep);
    put("prompt-editing", set.prompt_editing);
    // No music model on this machine means no song lengths to set.
    var row = $("music-length-row");
    if (row) row.hidden = !s.music;
  }

  $("filter-save").addEventListener("click", function () {
    saveSettings(FILTER_IDS, {
      screen_uploads: $("screen-uploads").checked ? 1 : 0,
      chat_strict: $("chat-strict").checked ? 1 : 0,
      music_strict: $("music-strict").checked ? 1 : 0
    }, "filter-saved");
  });

  $("lengths-save").addEventListener("click", function () {
    saveSettings(LENGTH_IDS, {
      video_min_seconds: num("vid-min", 5),
      video_max_seconds: num("vid-max", 15),
      video_default_seconds: num("vid-def", 5),
      video_max_seconds_sharp: num("vid-sharp", 10),
      music_min_seconds: num("mus-min", 10),
      music_max_seconds: num("mus-max", 120),
      music_default_seconds: num("mus-def", 30)
    }, "lengths-saved");
  });

  $("wording-save").addEventListener("click", function () {
    saveSettings(WORDING_IDS, {
      ui_lang: $("ui-lang").value,
      kid_pronoun: $("pronoun").value,
      app_title: $("app-title").value.trim()
    }, "wording-saved");
  });

  // How the helper models are held on the card, plus what the chat helper is
  // called. Its own Save rather than the models' one above it: choosing a
  // model and deciding how long it sits on the card are two decisions, and the
  // models' Save goes to a different route.
  $("held-save").addEventListener("click", function () {
    saveSettings(HELD_IDS, {
      script_keep_alive: $("h-script-keep").value.trim(),
      chat_keep_alive: $("h-chat-keep").value.trim(),
      comfy_free_after_job: $("h-free").checked ? 1 : 0,
      chat_name: $("h-chat-name").value.trim(),
      chat_keep_messages: num("h-chat-keep-msgs", 400)
    }, "held-saved");
  });

  $("stuff-save").addEventListener("click", function () {
    saveSettings(STUFF_IDS, {
      trash_days: num("trash-days", 7),
      max_characters: num("max-characters", 12),
      input_sweep_hours: num("sweep-hours", 24)
    }, "stuff-saved");
  });

  $("backup-keep-save").addEventListener("click", function () {
    saveSettings(BACKUP_IDS, { backup_keep: num("backup-keep", 7) },
                 "backup-keep-saved");
  });

  // --- how files are named --------------------------------------------------
  // The rows, the token list and the sample values all come from the server
  // (app/naming.py), so there is one copy of what a token means. What the page
  // owns is the substituting and the same validation the route does, which is
  // what makes the preview under each box live rather than a round trip per
  // keystroke.
  var NAME_TOKENS = ["date", "time", "kind", "who", "n", "idea", "seed"];
  var namingKinds = null, namingMax = 80;

  function nameToken() { return /\{([a-z]+)(?::(\d{1,2}))?\}/g; }

  function namePatternError(pattern) {
    pattern = (pattern || "").trim();
    if (!pattern) return "Give it a pattern, or put the default back.";
    if (pattern.length > namingMax) return "That is longer than " + namingMax + " characters.";
    var re = nameToken(), m, asked = {};
    while ((m = re.exec(pattern))) {
      if (NAME_TOKENS.indexOf(m[1]) === -1) return "There is no {" + m[1] + "}.";
      if (m[2] && m[1] !== "n") return "Only {n} can be padded with a number, not {" + m[1] + "}.";
      asked[m[1]] = true;
    }
    var rest = pattern.replace(nameToken(), "");
    if (/[/\\]/.test(rest)) return "A name cannot have a / or a \\ in it - everything lands in one folder.";
    if (/[^A-Za-z0-9._-]/.test(rest)) return "Letters, numbers, dots, dashes and underscores only.";
    if (pattern.charAt(0) === ".") return "A name cannot start with a dot - that hides the file.";
    if (!asked.n && !asked.time) return "Put {n} or {time} in it, or every file would want the same name.";
    return "";
  }

  // The same scrub app/naming.py does after substituting, so the preview is
  // the name and not an optimistic version of it.
  function nameFrom(pattern, sample) {
    var out = pattern.trim().replace(nameToken(), function (all, what, width) {
      var value = sample[what];
      if (value === undefined || value === null) return "";
      value = String(value);
      while (what === "n" && width && value.length < parseInt(width, 10)) value = "0" + value;
      return value;
    });
    out = out.replace(/[^A-Za-z0-9._-]+/g, "").replace(/^\.+/, "");
    out = out.replace(/([-_])[-_]+/g, "$1").replace(/^[-_]+/, "");
    return (out || "file") + sample.suffix;
  }

  function previewNames() {
    if (!namingKinds) return;
    namingKinds.forEach(function (k) {
      var box = $("name-" + k.id), eg = $("eg-" + k.id);
      if (!box || !eg) return;
      var wrong = namePatternError(box.value);
      eg.className = "eg" + (wrong ? " bad" : "");
      eg.textContent = wrong || ("the next one: " + nameFrom(box.value, k.sample));
    });
  }

  function buildNaming(info) {
    namingKinds = info.kinds;
    namingMax = info.max || namingMax;
    var rows = $("naming-rows");
    rows.textContent = "";
    info.kinds.forEach(function (k) {
      var row = document.createElement("div");
      row.className = "name-row";
      row.innerHTML =
        '<label class="label" for="name-' + esc(k.id) + '">' + esc(k.label) + '</label>' +
        '<input type="text" id="name-' + esc(k.id) + '" spellcheck="false" autocapitalize="off" ' +
        'autocorrect="off" maxlength="' + namingMax + '">' +
        '<div class="what">' + esc(k.what) + '</div>' +
        '<div class="eg" id="eg-' + esc(k.id) + '"></div>';
      rows.appendChild(row);
    });
    var list = $("naming-tokens");
    list.textContent = "";
    info.tokens.forEach(function (t) {
      var li = document.createElement("li");
      li.innerHTML = "<code>" + esc(t.token) + "</code><span>" + esc(t.what) + "</span>";
      list.appendChild(li);
    });
    var ids = info.kinds.map(function (k) { return "name-" + k.id; });
    watch(ids);
    ids.forEach(function (id) {
      $(id).addEventListener("input", function () {
        $("naming-error").textContent = "";
        previewNames();
      });
    });
  }

  function paintNaming(s) {
    if (!s.naming) return;
    if (!namingKinds) buildNaming(s.naming);
    s.naming.kinds.forEach(function (k) { put("name-" + k.id, k.pattern); });
    previewNames();
  }

  $("naming-save").addEventListener("click", function () {
    if (!namingKinds) return;     // the card has not been drawn yet
    var body = {}, wrong = "";
    namingKinds.forEach(function (k) {
      var value = $("name-" + k.id).value.trim();
      wrong = wrong || namePatternError(value);
      body[k.id] = value;
    });
    // All eight or none: the route refuses the lot on one bad pattern, and
    // sending them anyway only to be told so is a round trip for nothing.
    if (wrong) { $("naming-error").textContent = wrong; return; }
    $("naming-error").textContent = "";
    api("/api/parent/naming", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (info) {
      clean(namingKinds.map(function (k) { return "name-" + k.id; }));
      buildNaming(info);
      info.kinds.forEach(function (k) { put("name-" + k.id, k.pattern); });
      previewNames();
      $("naming-saved").hidden = false;
      setTimeout(function () { $("naming-saved").hidden = true; }, 1500);
      load();
    }).catch(function (e) {
      $("naming-error").textContent = e.message === "pin" ? "" : e.message;
    });
  });

  $("naming-defaults").addEventListener("click", function () {
    if (!namingKinds) return;
    namingKinds.forEach(function (k) {
      $("name-" + k.id).value = k.default;
      dirty["name-" + k.id] = true;
    });
    $("naming-error").textContent = "";
    previewNames();
  });

  $("quiz-bypass").addEventListener("change", function () {
    saveSettings(["quiz-bypass"], { quiz_bypass_minutes: num("quiz-bypass", 60) });
  });

  $("prompt-editing").addEventListener("change", function () {
    saveSettings(["prompt-editing"],
                 { prompt_editing: $("prompt-editing").checked ? 1 : 0 },
                 "prompt-editing-saved");
  });

  // --- backup and restore ---------------------------------------------------
  // The download needs the PIN header, so it cannot be a plain <a download>
  // the way the gallery zips are: fetch it, then hand the browser the blob.

  function paintBackups(list) {
    var box = $("backups");
    if (!box) return;
    $("backups-count").textContent = list.length ? "(" + list.length + ")" : "";
    if (!list.length) {
      box.innerHTML = "<p class='muted'>None yet. The first one is made tonight.</p>";
      return;
    }
    box.innerHTML = "";
    list.forEach(function (b) {
      var row = document.createElement("div");
      row.className = "row";
      var what = document.createElement("span");
      what.innerHTML = "<b>" + esc(when(b.made_at)) + "</b> · " + bytes(b.bytes) +
        (b.why === "nightly" ? " · nightly"
         : b.why === "before-restore" ? " · saved before a restore" : " · made by hand");
      row.appendChild(what);
      var go = document.createElement("button");
      go.textContent = "Restore this";
      armRestore(go, function () {
        return api("/api/parent/restore/saved", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: b.name })
        });
      }, $("restore-result"));
      row.appendChild(go);
      box.appendChild(row);
    });
  }

  // Two taps, eight seconds apart at most, and the button says what the second
  // one does. Restoring replaces every setting, every profile and every face.
  function armRestore(button, run, out) {
    var timer = null;
    var label = button.textContent;
    button.addEventListener("click", function () {
      if (timer) {
        clearTimeout(timer); timer = null;
        button.textContent = label;
        button.disabled = true;
        out.textContent = "Restoring...";
        run().then(function (r) {
          out.innerHTML = "<span class='ok'>Put back the backup from " +
            esc(r.made_at_text || "an earlier day") + ": " + r.settings_values +
            " setting" + (r.settings_values === 1 ? "" : "s") + ", " +
            r.profiles + " profile" + (r.profiles === 1 ? "" : "s") + ", " +
            r.avatars + " face" + (r.avatars === 1 ? "" : "s") +
            (r.safety_copy ? ". What was here is saved as " + esc(r.safety_copy) : "") +
            ".</span>";
          load();
        }).catch(function (e) {
          out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>";
        }).then(function () { button.disabled = false; });
        return;
      }
      out.innerHTML = "<span class='bad'>This replaces every setting, the " +
        "profiles, their faces, their characters and the prompt overrides with " +
        "what is in that file. The gallery is not touched.</span>";
      button.textContent = "Yes, replace it all";
      timer = setTimeout(function () {
        timer = null; button.textContent = label; out.textContent = "";
      }, 8000);
    });
  }

  $("backup-get").addEventListener("click", function () {
    var out = $("backup-result");
    out.textContent = "Building...";
    fetch("/api/parent/backup", { headers: pin ? { "X-Parent-Pin": pin } : {} })
      .then(function (r) {
        if (!r.ok) throw new Error("Could not build the backup");
        var name = "makery-backup.json";
        var head = r.headers.get("Content-Disposition") || "";
        var found = /filename="([^"]+)"/.exec(head);
        if (found) name = found[1];
        return r.blob().then(function (b) { return [b, name]; });
      })
      .then(function (pair) {
        var url = URL.createObjectURL(pair[0]);
        var a = document.createElement("a");
        a.href = url; a.download = pair[1];
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
        out.innerHTML = "<span class='ok'>Saved as " + esc(pair[1]) + ".</span>";
      })
      .catch(function (e) { out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; });
  });

  $("backup-now").addEventListener("click", function () {
    var b = $("backup-now"), out = $("backup-result");
    b.disabled = true;
    out.textContent = "Saving...";
    api("/api/parent/backup", { method: "POST" }).then(function (r) {
      out.innerHTML = "<span class='ok'>Kept as " + esc(r.name) + ".</span>";
      paintBackups(r.backups || []);
    }).catch(function (e) {
      out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>";
    }).then(function () { b.disabled = false; });
  });

  armRestore($("restore-go"), function () {
    var file = ($("restore-file").files || [])[0];
    if (!file) return Promise.reject(new Error("Choose a backup file first."));
    var form = new FormData();
    form.append("file", file);
    return api("/api/parent/restore", { method: "POST", body: form });
  }, $("restore-result"));

  // --- what was said in the chat -------------------------------------------
  // Loaded on its own rather than with the summary: a transcript can be a few
  // hundred lines and the summary reloads every thirty seconds.

  var chatLoaded = false;
  var kidName = "";
  fetch("/api/app").then(function (r) { return r.json(); }).then(function (d) {
    kidName = d.kid || "";
    if (d.title) document.title = d.title + " \u2014 parent page";
  }).catch(function () {});

  function paintChat(data) {
    var box = $("chat-transcript");
    var messages = data.messages || [];
    $("chat-count").textContent = messages.length
      ? "(" + messages.length + " lines, " + (data.today || 0) + " from " +
          (kidName || "your child") + " today)"
      : "(nothing yet)";
    if (!messages.length) {
      box.innerHTML = "<p class='muted'>" + esc(kidName || "Your child") +
        " hasn't used the chat tab yet.</p>";
      return;
    }
    box.innerHTML = messages.map(function (m) {
      var who = m.who === "helper" ? (data.name || "Helper")
        : (kidName || "Your child");
      return "<div class='chat-line " + esc(m.who) + (m.flagged ? " flagged" : "") + "'>" +
        "<time>" + esc(when(m.at || 0)) + "</time>" +
        "<span class='who'>" + esc(who) + "</span>" +
        "<span class='said'" + (m.flagged ? " data-flag='" + esc(m.flagged) + "'" : "") + ">" +
        esc(m.text) + "</span></div>";
    }).join("");
    // Newest last, so open it at the bottom - that is where today is.
    box.scrollTop = box.scrollHeight;
  }

  function loadChat() {
    return api("/api/parent/chat").then(function (data) {
      chatLoaded = true;
      paintChat(data);
    }).catch(function () {
      $("chat-transcript").innerHTML = "<p class='muted bad'>Couldn't read the transcript.</p>";
    });
  }

  var EVENT_WORD = {
    made: "every picture and video",
    limit: "running out for the day",
    digest: "the daily summary",
    flagged: "anything the filter stops",
    pin: "a wrong PIN on the parent page",
  };

  // One line per place, saying what that place gets. Which is worth showing
  // even with a single target: the tags are easy to typo and this is where
  // you find out you did.
  function paintRoutes(n) {
    var list = $("notify-routes");
    var routes = n.routes || [];
    list.hidden = !n.configured || !routes.length;
    if (list.hidden) { list.innerHTML = ""; return; }
    // Two Telegram bots would both read "tgram", so number them when a scheme
    // appears more than once. Which one is which is in .env, in order.
    var seen = {};
    routes.forEach(function (r) { seen[r.scheme] = (seen[r.scheme] || 0) + 1; });
    var nth = {};
    list.innerHTML = routes.map(function (r) {
      nth[r.scheme] = (nth[r.scheme] || 0) + 1;
      var where = r.scheme + (seen[r.scheme] > 1 ? " #" + nth[r.scheme] : "");
      var gets = r.all ? "everything"
        : r.events.map(function (e) { return EVENT_WORD[e] || e; }).join(", ");
      if (r.file && r.events.indexOf("made") !== -1) gets += ", with the file";
      return "<li><span class='where'>" + esc(where) + "</span>" +
             "<span class='gets'>" + esc(gets) + "</span></li>";
    }).join("");
  }

  function saveNotify() {
    api("/api/parent/notify", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        made: $("n-made").checked ? 1 : 0,
        attach: $("n-attach").checked ? 1 : 0,
        limit: $("n-limit").checked ? 1 : 0,
        digest: $("n-digest").checked ? 1 : 0,
        flagged: $("n-flagged").checked ? 1 : 0,
        pin: $("n-pin").checked ? 1 : 0,
        telegram: $("n-ask").checked ? 1 : 0,
        max_mb: num("n-maxmb", 20),
      }),
    }).then(function () {
      clean(["n-maxmb"]);
      $("notify-saved").hidden = false;
      setTimeout(function () { $("notify-saved").hidden = true; }, 1500);
      load();
    }).catch(function () {});
  }
  $("notify-save").addEventListener("click", saveNotify);
  // The attachment switch only means anything with the one above it on.
  $("n-made").addEventListener("change", function () { $("n-attach").disabled = !$("n-made").checked; });
  $("notify-test").addEventListener("click", function () {
    $("notify-result").textContent = "Sending\u2026";
    api("/api/parent/notify/test", { method: "POST" })
      .then(function (r) { $("notify-result").textContent = "Sent to " + r.targets.join(", ") + "."; })
      .catch(function (e) { $("notify-result").textContent = e.message || "Could not send it."; });
  });

  $("chat-refresh").addEventListener("click", function () { loadChat(); });
  $("chat-clear").addEventListener("click", function () {
    if (!window.confirm("Delete the whole chat transcript? You won't be able to read it back.")) return;
    api("/api/parent/chat", { method: "DELETE" }).then(function () {
      $("chat-cleared").textContent = "Deleted.";
      setTimeout(function () { $("chat-cleared").textContent = ""; }, 4000);
      loadChat();
    }).catch(function () {});
  });

  // --- what the app tells the models ----------------------------------------
  // Loaded once, when that tab is first opened: nineteen prompts is a few
  // kilobytes and most visits never look at them.

  var promptsLoaded = false;

  // A textarea does not size to its content, and these run from 400 to 3300
  // characters. Measured off scrollHeight when the row opens rather than
  // guessing rows: the CSS cap stops the longest from swallowing the screen.
  function fitPrompt(ta) {
    ta.style.height = "auto";
    ta.style.height = (ta.scrollHeight + 4) + "px";
  }

  function paintPrompts(data) {
    var box = $("prompts");
    box.innerHTML = "";
    $("prompts-editable").innerHTML = data.editable
      ? "You can edit these. A change takes effect on the next thing made — " +
        "no restart. <b>Reset</b> puts the built-in back."
      : "Read-only. Set <code>PROMPT_EDITING=1</code> in <code>.env</code> and " +
        "rebuild to make them editable.";

    (data.prompts || []).forEach(function (p) {
      var d = document.createElement("details");
      d.className = "pr";
      var tags = (p.safety ? '<span class="tag safety">safety</span>' : "") +
                 (p.overridden ? '<span class="tag changed">changed</span>' : "") +
                 '<span class="tag where">' + esc(p.where) + "</span>";
      d.innerHTML = "<summary>" + esc(p.label) + tags + "</summary>" +
        '<div class="body"><p class="blurb">' + esc(p.blurb) + "</p>" +
        (p.note ? '<p class="note">' + esc(p.note) + "</p>" : "") +
        "<textarea " + (data.editable ? "" : "readonly ") + "></textarea></div>";
      var ta = d.querySelector("textarea");
      ta.value = p.text;
      // Only once it is open: scrollHeight on a display:none element is 0.
      d.addEventListener("toggle", function () { if (d.open) fitPrompt(ta); });
      ta.addEventListener("input", function () { fitPrompt(ta); });

      if (data.editable) {
        var row = document.createElement("div");
        row.className = "row";
        var save = document.createElement("button");
        save.className = "primary";
        save.textContent = "Save";
        var reset = document.createElement("button");
        reset.textContent = "Reset to the built-in";
        reset.hidden = !p.overridden;
        var said = document.createElement("span");
        said.className = "muted";

        function send(value, done) {
          save.disabled = reset.disabled = true;
          api("/api/parent/prompts/" + encodeURIComponent(p.id), {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: value }),
          }).then(function (fresh) {
            ta.value = fresh.text;
            fitPrompt(ta);
            reset.hidden = !fresh.overridden;
            var t = d.querySelector(".tag.changed");
            if (fresh.overridden && !t) d.querySelector("summary").insertBefore(
              Object.assign(document.createElement("span"), { className: "tag changed", textContent: "changed" }),
              d.querySelector(".tag.where"));
            if (!fresh.overridden && t) t.remove();
            said.textContent = done;
            setTimeout(function () { said.textContent = ""; }, 3000);
          }).catch(function (err) {
            said.textContent = err.message || "Could not save that.";
          }).then(function () { save.disabled = reset.disabled = false; });
        }

        save.addEventListener("click", function () { send(ta.value, "Saved."); });
        reset.addEventListener("click", function () { send("", "Back to the built-in."); });
        row.appendChild(save); row.appendChild(reset); row.appendChild(said);
        d.querySelector(".body").appendChild(row);
      }
      box.appendChild(d);
    });
  }

  function loadPrompts() {
    return api("/api/parent/prompts").then(function (data) {
      promptsLoaded = true;
      paintPrompts(data);
    }).catch(function () {
      $("prompts").innerHTML = "<p class='muted bad'>Couldn't read them.</p>";
    });
  }

  // --- the machine, live ----------------------------------------------------
  // A canvas and one fetch a second, running only while the "Right now" tab is
  // the one on screen and the page is not in a background browser tab. A graph
  // nobody is looking at is a request a second forever.

  var LINES = [
    { key: "cpu", label: "Processor", colour: "#4fd1ff" },
    { key: "gpu", label: "Graphics", colour: "#56e39f" },
    { key: "vram", label: "Graphics memory", colour: "#ffb02e" },
    { key: "ram", label: "Memory", colour: "#ff6fd8" },
  ];
  var machineTimer = null;
  var machineSeen = [];
  var machineSpan = 180;   // seconds, as the server reports it

  function drawMachine(history, span) {
    var canvas = $("machine-graph");
    if (!canvas || !canvas.getContext) return;
    // Canvas pixels are not CSS pixels: without this it is a blurred graph on
    // every phone made in the last decade.
    var ratio = window.devicePixelRatio || 1;
    var width = canvas.clientWidth || 600;
    var height = 160;
    if (canvas.width !== Math.round(width * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    var g = canvas.getContext("2d");
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, width, height);

    var style = getComputedStyle(document.documentElement);
    var grid = (style.getPropertyValue("--card-edge") || "#4b3488").trim();
    g.strokeStyle = grid;
    g.lineWidth = 1;
    g.globalAlpha = 0.55;
    [0, 25, 50, 75, 100].forEach(function (pct) {
      var y = height - (pct / 100) * (height - 8) - 4;
      g.beginPath(); g.moveTo(0, y); g.lineTo(width, y); g.stroke();
    });
    g.globalAlpha = 1;

    if (!history.length) return;
    // Always the full window, so a line that has just started drawing walks in
    // from the right rather than stretching across and then shrinking.
    var newest = history[history.length - 1].t;
    var oldest = newest - span;
    LINES.forEach(function (line) {
      g.strokeStyle = line.colour;
      g.lineWidth = 2;
      g.beginPath();
      var started = false;
      history.forEach(function (point) {
        var value = point[line.key];
        if (value === null || value === undefined) { started = false; return; }
        var x = ((point.t - oldest) / span) * width;
        var y = height - (Math.max(0, Math.min(100, value)) / 100) * (height - 8) - 4;
        if (started) g.lineTo(x, y);
        else { g.moveTo(x, y); started = true; }
      });
      g.stroke();
    });
  }

  function mb(value) {
    if (value === null || value === undefined) return "";
    return value >= 1000 ? (value / 1000).toFixed(1) + " GB" : value + " MB";
  }

  function paintGauges(now) {
    var box = $("machine-now");
    if (!box) return;
    var cells = [
      { line: LINES[0], value: now.cpu_pct, sub: "of the whole machine" },
      { line: LINES[1], value: now.gpu_pct,
        sub: now.gpu_temp_c ? now.gpu_temp_c + "\u00b0C" : "" },
      { line: LINES[2],
        value: now.vram_total_mb ? Math.round(100 * now.vram_used_mb / now.vram_total_mb) : null,
        sub: now.vram_total_mb ? mb(now.vram_used_mb) + " of " + mb(now.vram_total_mb) : "no GPU" },
      { line: LINES[3],
        value: now.ram_total_mb ? Math.round(100 * now.ram_used_mb / now.ram_total_mb) : null,
        sub: now.ram_total_mb ? mb(now.ram_used_mb) + " of " + mb(now.ram_total_mb) : "" },
      { line: { label: "Disk", colour: "transparent" }, value: now.disk_used_pct,
        sub: now.disk_free_gb ? now.disk_free_gb + " GB free" : "" },
    ];
    box.innerHTML = cells.map(function (c) {
      return "<div class='gauge'><div class='what'>" +
        "<span class='key' style='background:" + c.line.colour + "'></span>" +
        esc(c.line.label) + "</div><div class='value'>" +
        (c.value === null || c.value === undefined ? "—" : Math.round(c.value) + "%") +
        "</div><div class='sub'>" + esc(c.sub || "") + "</div></div>";
    }).join("");
  }

  function pollMachine() {
    return api("/api/parent/stats").then(function (data) {
      machineSeen = data.history || [];
      machineSpan = data.seconds || machineSpan;
      drawMachine(machineSeen, machineSpan);
      paintGauges(data.now || {});
    }).catch(function () {});
  }

  function machineRunning(on) {
    if (machineTimer) { clearInterval(machineTimer); machineTimer = null; }
    if (!on) return;
    pollMachine();
    machineTimer = setInterval(pollMachine, 1000);
  }

  window.addEventListener("resize", function () {
    if (machineTimer) drawMachine(machineSeen, machineSpan);
  });
  document.addEventListener("visibilitychange", function () {
    machineRunning(!document.hidden && currentPTab === "now");
  });


  // --- the log --------------------------------------------------------------
  // Read-only, and there is deliberately nothing here that shortens it.

  var logLoaded = false, logPage = 0, logFilled = false;

  function logFilters(data) {
    if (logFilled) return;
    logFilled = true;
    var who = $("log-who");
    (data.actors || []).forEach(function (id) {
      var o = document.createElement("option");
      o.value = id;
      o.textContent = id === "parent" ? "the parent page"
        : id === "system" ? "the app itself"
        : id === "telegram" ? "the bot"
        : (people.filter(function (w) { return w.id === id; })[0] || {}).name || id;
      who.appendChild(o);
    });
    var kind = $("log-kind");
    (data.areas || []).forEach(function (a) {
      var o = document.createElement("option");
      o.value = a.id; o.textContent = a.label;
      kind.appendChild(o);
    });
  }

  function logQuery() {
    return "day=" + encodeURIComponent($("log-day").value || "") +
      "&who=" + encodeURIComponent($("log-who").value || "") +
      "&kind=" + encodeURIComponent($("log-kind").value || "") +
      "&page=" + logPage + "&limit=50";
  }

  function loadLog() {
    logLoaded = true;
    return api("/api/parent/log?" + logQuery()).then(function (data) {
      logFilters(data);
      paintLog(data);
      put("log-keep", String(data.keep_days || 0));
      put("log-words", !!data.keep_words);
    }).catch(function () {});
  }

  function bits(details) {
    var out = [];
    Object.keys(details || {}).sort().forEach(function (k) {
      var v = details[k];
      out.push(k + ": " + (typeof v === "object" ? JSON.stringify(v) : String(v)));
    });
    return out.join(" · ");
  }

  function actorName(id) {
    if (id === "parent") return "The parent page";
    if (id === "system") return "The app";
    if (id === "telegram") return "The bot";
    var who = people.filter(function (w) { return w.id === id; })[0];
    return who ? who.name : id;
  }

  function paintLog(data) {
    var box = $("log-rows");
    box.innerHTML = "";
    if (!data.entries.length) {
      box.innerHTML = '<p class="muted">Nothing matches that.</p>';
      $("log-paging").hidden = true;
      return;
    }
    data.entries.forEach(function (e) {
      var row = document.createElement("div");
      row.className = "log-row";
      row.innerHTML =
        '<span class="when">#' + e.id + " · " + esc(when(e.at)) + '</span> ' +
        '<span class="who">' + esc(actorName(e.actor)) + "</span> " +
        esc(e.says) +
        (bits(e.details) ? '<span class="bits">' + esc(bits(e.details)) + "</span>" : "") +
        '<span class="seal">' + esc(e.hash.slice(0, 16)) + "</span>";
      box.appendChild(row);
    });
    var first = data.offset + 1, last = data.offset + data.entries.length;
    $("log-where").textContent = first + "–" + last + " of " + data.total;
    $("log-prev").disabled = data.offset <= 0;
    $("log-next").disabled = last >= data.total;
    $("log-paging").hidden = false;
  }

  ["log-day", "log-who", "log-kind"].forEach(function (id) {
    $(id).addEventListener("change", function () { logPage = 0; loadLog(); });
  });
  $("log-clear").addEventListener("click", function () {
    $("log-day").value = ""; $("log-who").value = ""; $("log-kind").value = "";
    logPage = 0; loadLog();
  });
  $("log-prev").addEventListener("click", function () {
    if (logPage > 0) { logPage -= 1; loadLog(); }
  });
  $("log-next").addEventListener("click", function () { logPage += 1; loadLog(); });

  $("log-check").addEventListener("click", function () {
    var b = $("log-check"), out = $("log-verdict");
    b.disabled = true;
    out.textContent = "Checking every entry...";
    api("/api/parent/log/verify").then(function (r) {
      out.innerHTML = "<span class='" + (r.ok ? "ok" : "bad") + "'>" +
        esc(r.says) + "</span>" +
        (r.ok && r.checked ? "<br><span class='muted small'>Last seal: " +
          esc(r.last_hash) + "</span>" : "");
    }).catch(function (e) {
      out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>";
    }).then(function () { b.disabled = false; });
  });

  function downloadLog(kind) {
    var out = $("log-verdict");
    out.textContent = "Building...";
    fetch("/api/parent/log/export?kind=" + kind,
          { headers: pin ? { "X-Parent-Pin": pin } : {} })
      .then(function (r) {
        if (!r.ok) throw new Error("Could not build the download");
        var name = "makery-log." + kind;
        var found = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") || "");
        if (found) name = found[1];
        return r.blob().then(function (b) { return [b, name]; });
      })
      .then(function (pair) {
        var url = URL.createObjectURL(pair[0]);
        var a = document.createElement("a");
        a.href = url; a.download = pair[1];
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
        out.innerHTML = "<span class='ok'>Saved as " + esc(pair[1]) + ".</span>";
      })
      .catch(function (e) { out.innerHTML = "<span class='bad'>" + esc(e.message) + "</span>"; });
  }
  $("log-csv").addEventListener("click", function () { downloadLog("csv"); });
  $("log-jsonl").addEventListener("click", function () { downloadLog("jsonl"); });

  function saveLogSettings() {
    api("/api/parent/log/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keep_days: parseFloat($("log-keep").value) || 0,
        keep_words: $("log-words").checked ? 1 : 0
      })
    }).then(function () {
      var saved = $("log-saved");
      saved.hidden = false;
      setTimeout(function () { saved.hidden = true; }, 1600);
      loadLog();
    }).catch(function () {});
  }
  $("log-keep").addEventListener("change", saveLogSettings);
  $("log-words").addEventListener("change", saveLogSettings);

  // --- which model does which job -------------------------------------------
  // Loaded when the Right now tab is opened, not with the summary: it asks
  // Ollama two questions, and the summary already runs every thirty seconds.
  var helpersLoaded = false, helpers = null;

  function gb(mb) {
    if (!mb) return "";
    return mb >= 1000 ? (mb / 1000).toFixed(1) + " GB" : Math.round(mb) + " MB";
  }

  // What a model is, in one line: 7.6 GB · 11.9B · gemma4 · can see pictures.
  function modelLine(m) {
    var bits = [];
    if (m.size_mb) bits.push(gb(m.size_mb));
    if (m.parameter_size) bits.push(m.parameter_size);
    if (m.family) bits.push(m.family);
    if (m.vision) bits.push("can look at pictures");
    else if (m.vision === false) bits.push("words only");
    if (m.loaded) bits.push("loaded now" + (m.vram_mb ? ", " + gb(m.vram_mb) + " of card" : ""));
    return bits.join(" \u00b7 ");
  }

  function byName(name) {
    var found = null;
    (helpers && helpers.models || []).forEach(function (m) { if (m.name === name) found = m; });
    return found;
  }

  function paintHelperNote(role) {
    var note = $("helper-note-" + role.id);
    if (!note) return;
    var chosen = $("helper-" + role.id).value;
    var using = chosen || role.in_use;
    var m = byName(using);
    note.className = "note muted";
    if (!m) {
      note.className = "note bad";
      note.textContent = "Ollama has not got \u201c" + using + "\u201d. Pull it " +
        "with `ollama pull " + using + "`, or pick one from the list.";
      return;
    }
    var line = modelLine(m);
    if (role.needs_vision && m.vision === false) {
      note.className = "note warn";
      note.textContent = line + " \u2014 but it cannot see. \u201cHelp me write " +
        "it\u201d on one of their own pictures will be answered from words " +
        "alone, so what comes back is about a picture the model was never " +
        "shown; saving a character reads its face the same way, and the check " +
        "on an uploaded photo is the same model looking at it. Everything " +
        "from words alone still works. Pick a vision model for the idea helper.";
      return;
    }
    note.textContent = line;
  }

  function paintHelpers(data) {
    helpers = data;
    var box = $("helpers-roles");
    $("helpers-state").innerHTML = data.reachable
      ? (data.models.length + " model" + (data.models.length === 1 ? "" : "s") +
         " pulled on this machine." +
         (data.busy ? " <b>Something is rendering</b>, so Test is off until it finishes." : ""))
      : "<span class='bad'>Ollama did not answer</span> \u2014 nothing can be " +
        "chosen until it does. Whatever is set stays set.";
    box.innerHTML = "";
    (data.roles || []).forEach(function (role) {
      var row = document.createElement("div");
      row.className = "helper";
      var options = (data.models || []).map(function (m) {
        return "<option value='" + esc(m.name) + "'>" + esc(m.name) +
               (m.size_mb ? " \u2014 " + esc(gb(m.size_mb)) : "") + "</option>";
      });
      // A name Ollama has not got is still what is in force, so it has to be
      // in the list or the dropdown would quietly say something else.
      if (role.in_use && !byName(role.in_use)) {
        options.unshift("<option value='" + esc(role.in_use) + "'>" + esc(role.in_use) +
                        " \u2014 not pulled</option>");
      }
      if (role.follows) {
        options.unshift("<option value=''>The same as the idea helper</option>");
      }
      row.innerHTML =
        "<div class='top'><span class='name'>" + esc(role.label) + "</span>" +
        "<select id='helper-" + esc(role.id) + "'>" + options.join("") + "</select>" +
        "<button data-try='" + esc(role.id) + "'" + (data.busy || !data.reachable ? " disabled" : "") +
        ">Test</button></div>" +
        "<p class='what'>" + esc(role.what) + "</p>" +
        "<p class='note muted' id='helper-note-" + esc(role.id) + "'></p>" +
        "<p class='tried' id='helper-tried-" + esc(role.id) + "' hidden></p>";
      box.appendChild(row);
      var select = row.querySelector("select");
      select.value = role.chosen;
      if (select.selectedIndex < 0) select.value = role.in_use;
      select.addEventListener("change", function () { paintHelperNote(role); });
      paintHelperNote(role);
    });
    $("helpers-save").disabled = !data.reachable;
  }

  function loadHelpers() {
    return api("/api/parent/models").then(function (data) {
      helpersLoaded = true;
      paintHelpers(data);
    }).catch(function () {});
  }

  $("helpers-save").addEventListener("click", function () {
    var body = {};
    (helpers && helpers.roles || []).forEach(function (role) {
      body[role.id] = $("helper-" + role.id).value;
    });
    $("helpers-result").textContent = "";
    api("/api/parent/models", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (data) {
      paintHelpers(data);
      $("helpers-saved").hidden = false;
      setTimeout(function () { $("helpers-saved").hidden = true; }, 1500);
    }).catch(function (e) {
      $("helpers-result").textContent = e.message || "Could not save it.";
    });
  });

  // One short question through whichever model that job is on now - the saved
  // one, so Test after Save is what they will actually get.
  $("helpers-roles").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-try]");
    if (!b) return;
    var id = b.dataset.try, out = $("helper-tried-" + id);
    out.hidden = false;
    out.textContent = "Asking it\u2026 the first answer pays for loading the model.";
    b.disabled = true;
    api("/api/parent/models/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: id })
    }).then(function (r) {
      var speed = r.tokens_per_sec ? r.tokens_per_sec + " words-ish a second" : "";
      if (r.tokens_per_sec && !r.looked_gpu_accelerated) speed += " (that is CPU slow)";
      out.innerHTML = "<b>" + esc(r.model) + "</b> said: \u201c" + esc(r.reply) + "\u201d" +
        (speed ? " \u00b7 " + esc(speed) : "") +
        (r.total_seconds ? " \u00b7 " + esc(r.total_seconds + "s in all") : "");
    }).catch(function (err) {
      out.textContent = err.message || "It did not answer.";
    }).then(function () { b.disabled = false; });
  });

  // Tabs, like the main page. Remembered, so a parent checking the trash
  // every evening lands on the trash.
  var ptabBar = document.querySelector(".ptabs");
  var currentPTab = "now";
  function showPTab(name) {
    if (!document.querySelector('.ptab[data-tab="' + name + '"]')) name = "now";
    document.querySelectorAll(".ptab").forEach(function (t) { t.hidden = t.dataset.tab !== name; });
    document.querySelectorAll(".ptab-btn").forEach(function (b) {
      var on = b.dataset.tab === name;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    try { localStorage.setItem("parent-tab", name); } catch (e) {}
    currentPTab = name;
    if (name === "words" && !promptsLoaded) loadPrompts();
    if (name === "log") loadLog();
    if (name === "settings" && !helpersLoaded) loadHelpers();
    machineRunning(name === "now" && !document.hidden);
  }
  if (ptabBar) {
    ptabBar.addEventListener("click", function (e) {
      var b = e.target.closest(".ptab-btn");
      if (b) showPTab(b.dataset.tab);
    });
    var startTab = "now";
    try { startTab = localStorage.getItem("parent-tab") || "now"; } catch (e) {}
    showPTab(startTab);
  }

  load().then(function () { if (!chatLoaded) loadChat(); }).catch(function () {});
  setInterval(function () { if (!$("body").hidden) load().catch(function () {}); }, 30000);
})();
