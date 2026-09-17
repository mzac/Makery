/* Makery frontend.
   Two cards: a picture maker, and a video maker that starts from either words
   or a picture, plus a gallery of everything made so far. One job runs at a
   time, so while anything is generating every start button is locked and a
   Stop button appears; a reload reattaches to it. Every string they can see
   stays friendly. */

(function () {
  "use strict";

  var POLL_MS = 1500;

  // What this instance is called. Neutral in the markup, filled in from
  // /api/app, so the child's name lives in the environment and not the repo.
  var appTitle = t("My AI Factory");
  var appKid = "";

  // Say what happened, to the container log. The iPad is the only witness to
  // anything that goes wrong on the iPad.
  function report(where, detail) {
    try {
      fetch("/api/client-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ where: String(where), detail: String(detail).slice(0, 400) }),
        keepalive: true,
      }).catch(function () {});
    } catch (e) { /* never let reporting be the thing that breaks */ }
  }

  window.addEventListener("error", function (e) {
    report("js-error", (e.message || "?") + " @ " + (e.filename || "?") + ":" + (e.lineno || 0));
  });
  window.addEventListener("unhandledrejection", function (e) {
    report("js-reject", (e.reason && (e.reason.message || e.reason)) || "?");
  });
  var GENERIC_ERROR = t("Something went wrong. Let's try that again!");

  // The picture chosen for the video card: a finished job, or anything in the
  // gallery - a generated picture, an uploaded photo or drawing, or a video
  // (which means its last frame).
  var source = null; // {jobId} | {galleryId}

  var cards = {};
  Array.prototype.forEach.call(document.querySelectorAll(".card[data-kind]"), function (el) {
    cards[el.dataset.kind] = {
      kind: el.dataset.kind,
      el: el,
      textarea: el.querySelector("textarea"),
      button: el.querySelector(".go"),
      stop: el.querySelector(".stop"),
      helper: el.querySelector(".helper"),
      surprise: el.querySelector(".surprise"),
      clearText: el.querySelector(".clear-text"),
      reset: el.querySelector(".card-reset"),
      say: el.querySelector(".say-input"),
      helperMsg: el.querySelector(".helper-msg"),
      status: el.querySelector(".status"),
      bar: el.querySelector(".bar"),
      fill: el.querySelector(".fill"),
      pct: el.querySelector(".pct"),
      msg: el.querySelector(".msg"),
      timing: el.querySelector(".timing"),
      sys: el.querySelector(".sys"),
      allowance: el.querySelector(".allowance"),
      etaNote: el.querySelector(".eta-note"),
      length: el.querySelector(".length-slider"),
      lengthOut: el.querySelector(".length-out"),
      orients: el.querySelectorAll(".orient"),
      counts: el.querySelectorAll(".count-pick"),
      panelCounts: el.querySelectorAll(".panels"),
      partsBox: el.querySelector(".parts"),
      effectRow: el.querySelector(".effect-row"),
      qualPicks: el.querySelectorAll(".qual-pick"),
      qualMax: el.querySelector(".qual-max"),
      effectPick: el.querySelector(".effect-pick"),
      effectWhen: el.querySelector(".effect-when"),
      partPicks: el.querySelectorAll(".part-pick"),
      kindPicks: el.querySelectorAll(".kind-pick"),
      singPicks: el.querySelectorAll(".sing-pick"),
      // The music card's "What kind of sound". Deliberately not `.kind-pick`,
      // which is the picture card's "a picture or a character" - these are
      // looked up per card by class, so two cards must not share one.
      soundKinds: el.querySelector(".sound-kind-picks"),
      soundKindNote: el.querySelector(".sound-kind-note"),
      singRow: el.querySelector(".setting.sing-row"),
      lyrics: el.querySelector(".lyrics"),
      clearLyrics: el.querySelector(".clear-lyrics"),
      wordsRow: el.querySelector(".setting.words"),
      kindNote: el.querySelector(".kind-note"),
      cast: el.querySelector(".cast"),
      history: el.querySelector(".history"),
      historyList: el.querySelector(".history-list"),
      castRow: el.querySelector(".cast-row"),
      modes: el.querySelectorAll(".opt"),
      dropdowns: el.querySelector(".dropdowns"),
      result: el.querySelector(".result"),
      timer: null,
      seconds: 5,
      orientation: "landscape",
      count: 1,
      panels: 4,
      parts: 3,
      cutout: false,
      singing: true,
      soundKind: "song",
      soundKindList: [],
      quality: "normal",
      character: "",
      jobId: null,
      lastBody: null,   // what was last sent, for "Try again"
      tweakSeed: null,  // set by "make it again, but...", spent on the next go
    };
  });

  // --- what is happening right now -------------------------------------------
  // Under the banner, on every tab. The tab dot says *something* is going; this
  // says what it is and how far along, so they can wander off to the gallery
  // without losing sight of their video.

  var nowBar = document.getElementById("nowbar");
  var nowMain = document.getElementById("nowbar-main");
  var nowText = document.getElementById("nowbar-text");
  var nowGo = document.getElementById("nowbar-go");

  var WHAT = { image: "picture", t2v: "video", i2v: "video", flf: "video", comic: "comic",
               story: "film", music: "song", jingle: "tune", ambience: "sound",
               // Started from the gallery rather than from a maker card.
               smooth: "smooth video", slowmo: "slow-motion video", huge: "big picture",
               edit: "changed picture", outpaint: "bigger picture", inpaint: "picture",
               restyle: "picture" };

  function showNow(card, job) {
    if (!card || !job) { hideNow(); return; }
    var what = WHAT[job.kind] || "picture";
    var pct = Math.round((job.progress || 0) * 100);
    var line = (job.message || t("Working...")) + (pct ? "  " + pct + "%" : "");
    nowText.textContent = line;
    nowBar.classList.remove("idle");
    // Only worth offering when they are looking at something else.
    nowGo.hidden = currentTab === (TAB_FOR_KIND[job.kind] || "image");
    nowGo.onclick = function () { showTab(TAB_FOR_KIND[job.kind] || "image"); };
    nowBar.hidden = false;
    // Whatever the bar is about, the sheet behind it is about the same thing.
    nowJob = job;
    nowOwner = card;
    if (!nowSheet.hidden) paintNow();
  }

  function hideNow() {
    nowBar.hidden = true;
    nowGo.onclick = null;
    // They may be reading the sheet when a job ends. It stays, saying it is
    // done, with the way to the thing it made: closing a page somebody is
    // looking at is its own small bug.
    if (nowSheet.hidden || !nowJob || nowJob.status !== "done") {
      nowJob = null;
      nowOwner = null;
      closeNowSheet();
    }
  }

  // A finished job leaves the bar up for a moment rather than vanishing, so
  // "it's done" is something they see rather than something they miss.
  function finishNow(job) {
    var what = WHAT[job.kind] || "picture";
    // One key per kind rather than a noun dropped into one sentence: "ready"
    // agrees with what is ready in French, and "prête" for a picture is not
    // "prêt" for a film.
    nowText.textContent = t("Your " + what + " is ready! \u2728");
    nowBar.classList.add("idle");
    nowGo.hidden = currentTab === (TAB_FOR_KIND[job.kind] || "image");
    nowBar.hidden = false;
    nowJob = job;
    if (!nowSheet.hidden) paintNow();
    setTimeout(function () { if (!activeCard) hideNow(); }, 8000);
  }

  // --- the whole story, behind the bar --------------------------------------
  // "Nearly there" is the right amount to read on a page they are doing
  // something else on, and the wrong amount when they want to know whether it
  // is stuck. So the bar is a button, and this is what it opens: what is being
  // made, in their own words, how big, how far along, what the machine is doing
  // about it, and the two ways out - Stop, or go and watch.

  var nowSheet = document.getElementById("nowsheet");
  var nowMaking = document.getElementById("now-making");
  var nowIdea = document.getElementById("now-idea");
  var nowFacts = document.getElementById("now-facts");
  var nowFill = document.getElementById("now-fill");
  var nowPct = document.getElementById("now-pct");
  var nowStep = document.getElementById("now-step");
  var nowTimes = document.getElementById("now-times");
  var nowQueue = document.getElementById("now-queue");
  var nowSys = document.getElementById("now-sys");
  var nowShow = document.getElementById("now-show");
  var nowStop = document.getElementById("now-stop");

  // The job the bar is about, and whose card its Stop belongs to. Both are set
  // by showNow, which every path already goes through - the maker cards, the
  // renders they start from their gallery, and reattaching after a reload.
  var nowJob = null;
  var nowOwner = null;
  var nowTimer = null;

  // One key per kind rather than a noun dropped into one sentence, for exactly
  // the reason "your video is ready" needs one: French agrees the article with
  // what is being made, and "un film" is not "une image".
  var MAKING = {
    image: "Making a picture",
    comic: "Making a comic",
    t2v: "Making a video", i2v: "Making a video", flf: "Making a video",
    story: "Making a film",
    music: "Making a song",
    jingle: "Making a little tune",
    ambience: "Making a background hum",
    smooth: "Making a video smoother",
    slowmo: "Making a video slow",
    huge: "Making a picture huge",
    edit: "Changing a picture",
    outpaint: "Seeing outside a picture",
    inpaint: "Fixing part of a picture",
    restyle: "Turning a picture into something else",
  };

  // The quality picker's own words without their emoji: three chips in a row
  // of facts is enough decoration.
  var QUALITY_WORDS = { quick: "Quick", normal: "Normal", sharp: "Sharper" };

  // The size, the length, the quality, which one of how many, and what is
  // drawing it. Anything the job does not know about itself is simply left
  // out - a song has no size and a picture has no length.
  function nowFactWords(job) {
    var chips = [];
    if (job.size) chips.push(job.size);
    if (job.duration) chips.push(t("{n} secs", { n: job.duration }));
    if (QUALITY_WORDS[job.quality]) chips.push(t(QUALITY_WORDS[job.quality]));
    if (job.steps > 1) {
      chips.push(t("{n} of {m}", { n: Math.max(1, job.step || 1), m: job.steps }));
    }
    // A model name is a proper noun and stays English, like the helper's.
    if (job.model) chips.push(job.model);
    return chips;
  }

  function nowTimeWords(job) {
    var parts = [];
    if (job.elapsed > 2) parts.push(t("{time} so far", { time: clock(job.elapsed) }));
    if (job.status === "done") return parts;
    if (job.eta !== null && job.eta !== undefined && job.eta > 5) {
      parts.push(t("about {time} to go", { time: clock(job.eta) }));
    } else if (job.estimate && job.estimate.seconds) {
      // The smoothed ETA deliberately says nothing for the first eight
      // seconds, because they are a model load and not a rate. This is what
      // the machine's own history says the whole thing takes, which is the
      // honest thing to have there in the meantime.
      parts.push(t("usually takes {time}", { time: clock(job.estimate.seconds) }));
    }
    return parts;
  }

  function paintNow() {
    var job = nowJob;
    if (!job) return;
    var done = job.status === "done";
    nowMaking.textContent = t(MAKING[job.kind] || "Making something");

    // Their own words, and never translated: a sentence they typed in English is
    // theirs in English. `idea` rather than `prompt` for the same reason the
    // viewer prefers it - the composed prompt is English by construction.
    var idea = (job.idea || "").trim();
    nowIdea.textContent = idea ? "\u201c" + idea + "\u201d" : "";
    nowIdea.hidden = !idea;

    nowFacts.innerHTML = "";
    nowFactWords(job).forEach(function (word) {
      var li = document.createElement("li");
      li.textContent = word;
      nowFacts.appendChild(li);
    });

    var pct = Math.round((done ? 1 : job.progress || 0) * 100);
    nowFill.style.width = pct + "%";
    nowPct.textContent = pct + "%";
    nowStep.textContent = done ? t("Done! \u2728") : (job.message || t("Working..."));

    var times = nowTimeWords(job);
    nowTimes.textContent = times.join("  \u00b7  ");
    nowTimes.hidden = times.length === 0;

    nowShow.textContent = done ? t("Look at it!") : t("Show me");
    nowShow.hidden = false;

    // No Stop on a render they started from their gallery: ten seconds is not
    // worth a button, which is the decision those were built with and not a
    // gap here. Nor on one that is already over.
    var stoppable = !done && job.cancellable && nowOwner && nowOwner.stop;
    if (!stoppable && armed === nowStop) disarm();
    nowStop.hidden = !stoppable;
    if (stoppable) nowStop.disabled = false;
  }

  // The live numbers, on their own two-second clock: the job poll carries them
  // too, but the sheet stays open for a moment after the job has finished,
  // when nothing is polling any more.
  function tickNow() {
    if (nowSheet.hidden) return;
    fetch("/api/now").then(readJSON).then(function (data) {
      if (nowSheet.hidden || !data) return;
      showSystem({ sys: nowSys }, { system: data.system });
      var ahead = data.ahead;
      if (ahead && nowJob && nowJob.status !== "done") {
        nowQueue.textContent = ahead === 1
          ? t("Something else is being made first.")
          : t("There are {n} things being made first.", { n: ahead });
        nowQueue.hidden = false;
      } else {
        nowQueue.hidden = true;
      }
    }).catch(function () { /* a blip should not empty the sheet */ });
  }

  function openNowSheet() {
    if (!nowJob) return;
    nowSheet.hidden = false;
    nowMain.setAttribute("aria-expanded", "true");
    lockPage();
    paintNow();
    nowQueue.hidden = true;
    tickNow();
    clearInterval(nowTimer);
    // Two seconds. The sampler behind /api/now refreshes once a second, and
    // this is a number to glance at rather than a graph.
    nowTimer = setInterval(tickNow, 2000);
  }

  function closeNowSheet() {
    clearInterval(nowTimer);
    nowTimer = null;
    if (nowSheet.hidden) return;
    nowSheet.hidden = true;
    nowMain.setAttribute("aria-expanded", "false");
    if (armed === nowStop) disarm();
    // The bar has already gone: whatever they were reading about is over.
    if (nowBar.hidden) { nowJob = null; nowOwner = null; }
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  nowMain.addEventListener("click", openNowSheet);

  nowShow.addEventListener("click", function () {
    var job = nowJob;
    closeNowSheet();
    if (!job) return;
    // A render they started from their gallery has no card to go back to, so
    // "Look at it!" opens the thing itself, the way its toast does.
    if (job.status === "done" && TAB_FOR_KIND[job.kind] === "mine" && job.filename) {
      openViewerById(job.filename);
      return;
    }
    showTab(TAB_FOR_KIND[job.kind] || "image");
  });

  nowStop.addEventListener("click", function () {
    if (!arm(nowStop, t("Really stop?"))) return;
    disarm();
    var owner = nowOwner;
    closeNowSheet();
    // The card's own Stop, not a second way of stopping things: it knows about
    // four at once keeping what has already landed.
    if (owner && owner.stop) stop(owner);
  });

  // --- one card at a time ---------------------------------------------------
  // Four tall cards meant the one they wanted was usually below the fold. The
  // tabs show one at a time and remember which, so coming back lands where they
  // left off. Anything that needs a particular card - "Animate this",
  // reattaching to a running job - calls showTab itself rather than hoping they
  // is already looking at the right one.

  var TAB_FOR_KIND = { image: "image", t2v: "video", i2v: "video", flf: "video", comic: "comic",
                       story: "video", music: "music",
                       // The other two "What kind of sound" chips. Same card,
                       // same tab; only what lands in the gallery differs.
                       jingle: "music", ambience: "music",
                       // These three have no maker card - what they make turns
                       // up in the Gallery, so that is where "Show me" goes.
                       smooth: "mine", slowmo: "mine", huge: "mine",
                       // Started from the viewer too, and what they make lands
                       // in the Gallery beside the picture they came from.
                       edit: "mine", outpaint: "mine", inpaint: "mine",
                       restyle: "mine" };
  var tabBar = document.getElementById("tabs");
  var currentTab = "image";

  // Which makers exist, as the server last said. A parent can switch one off,
  // and a machine can simply not have the model for it; either way the tab
  // goes. The routes refuse regardless - this is only so they are not looking at
  // a tab that answers "switched off" on every tap.
  var moduleOn = { picture: true, video: true, comic: true, music: true, chat: true,
                   story: true };
  // Which of the story maker's borrowed steps this installation can run. A
  // switched-off maker takes one step out of the flow rather than the tab -
  // except the film, which is handled below, because a story with no film is
  // the picture and the song they could have made on their own cards.
  var storySteps = { picture: true, video: true, music: true };

  // Which tab belongs to which maker. "mine" and "banner" are theirs whatever
  // is switched off - their gallery and their colours are not a maker.
  var TAB_MODULE = { image: "picture", video: "video", comic: "comic",
                     music: "music", story: "story", chat: "chat" };

  function applyModules(states, steps) {
    Object.keys(states || {}).forEach(function (id) { moduleOn[id] = !!states[id]; });
    if (steps) Object.keys(steps).forEach(function (id) { storySteps[id] = !!steps[id]; });
    // The story maker borrows the video maker and cannot do without it: every
    // other step is skippable, and a "story" that is one picture and a song is
    // two other cards' work with extra taps. So the tab goes with the film.
    moduleOn.story = moduleOn.story && storySteps.video;
    if (cards.story) sayWhatIsOff();
    Object.keys(TAB_MODULE).forEach(function (tab) {
      var button = tabBar.querySelector('.tab[data-tab="' + tab + '"]');
      if (button) button.hidden = !moduleOn[TAB_MODULE[tab]];
    });
    // The banner maker in Settings makes a picture, so it goes with pictures.
    var banner = cards.banner;
    if (banner) {
      ["idea", "settings", "buttons"].forEach(function (part) {
        var el = banner.el.querySelector("." + part);
        if (el) el.hidden = !moduleOn.picture;
      });
      if (banner.etaNote && !moduleOn.picture) banner.etaNote.hidden = true;
      if (banner.allowance && !moduleOn.picture) banner.allowance.hidden = true;
      // Say what they *can* still do, rather than leaving a gap where the
      // maker was: any picture in their gallery can go up there.
      var why = document.getElementById("banner-off");
      if (why) why.hidden = moduleOn.picture;
    }
    // A remembered tab that no longer exists would leave them on a blank page.
    if (TAB_MODULE[currentTab] && !moduleOn[TAB_MODULE[currentTab]]) showTab(firstTab());
    if (moduleOn.music && cards.music) setSinging(cards.music, cards.music.singing);
  }

  // Whatever is left, in the order they appear. Everything can be off.
  function firstTab() {
    var found = Object.keys(TAB_MODULE).filter(function (t) {
      return moduleOn[TAB_MODULE[t]];
    })[0];
    return found || "mine";
  }

  function showTab(name, opts) {
    if (TAB_MODULE[name] && !moduleOn[TAB_MODULE[name]]) name = firstTab();
    // "mine" and "chat" are cards without a data-kind: nothing generates from
    // them, so they are not in the `cards` map that everything else uses.
    if (!cards[name] && name !== "mine" && name !== "chat") return;
    currentTab = name;
    Array.prototype.forEach.call(tabBar.querySelectorAll(".tab"), function (t) {
      var on = t.dataset.tab === name;
      t.classList.toggle("is-on", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (mineCard) mineCard.hidden = name !== "mine";
    // The choose-things bar is fixed to the bottom of the screen and has no
    // business hovering over another card.
    if (name !== "mine" && choosing) setChoosing(false);
    if (chatCard) chatCard.hidden = name !== "chat";
    if (name === "chat") onChatShown();
    Object.keys(cards).forEach(function (kind) {
      cards[kind].el.hidden = kind !== name;
    });
    try { localStorage.setItem("makery:tab", name); } catch (e) {}
    if (!opts || !opts.keepScroll) window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // A dot on the tab of whatever is rendering, so switching away does not feel
  // like walking out on it.
  function markWorkingTab() {
    var busy = activeCard ? TAB_FOR_KIND[activeCard.kind] || activeCard.kind : null;
    Array.prototype.forEach.call(tabBar.querySelectorAll(".tab"), function (t) {
      t.classList.toggle("working", t.dataset.tab === busy);
    });
  }

  // The bar is transparent until it is actually stuck over content. A sentinel
  // just above it is the cheap way to know: no scroll handler, no layout reads.
  (function watchStuck() {
    var sentinel = document.getElementById("tabs-sentinel");
    if (!sentinel || !window.IntersectionObserver) return;
    new IntersectionObserver(function (entries) {
      tabBar.classList.toggle("stuck", !entries[0].isIntersecting);
    }).observe(sentinel);
  })();

  tabBar.addEventListener("click", function (e) {
    var tab = e.target.closest(".tab");
    if (tab) showTab(tab.dataset.tab);
  });

  // --- what they have typed survives a reload --------------------------------
  // Losing a carefully typed idea to a stray reload, a tab switch that drops
  // the page, or an iPad deciding to reclaim memory is a small thing that
  // feels like a big one. Kept in localStorage, per box, and cleared when they
  // clear the box themselves. Every access is wrapped: Safari throws on
  // localStorage in a private window rather than returning null.

  function recall(key) {
    try { return localStorage.getItem("makery:" + key) || ""; } catch (e) { return ""; }
  }

  function keep(key, value) {
    try {
      if (value) localStorage.setItem("makery:" + key, value);
      else localStorage.removeItem("makery:" + key);
    } catch (e) { /* full, or private browsing: not worth telling them about */ }
  }

  function remember(el, key, after) {
    if (!el) return;
    var saved = recall(key);
    if (saved && !el.value) el.value = saved;
    el.addEventListener("input", function () { keep(key, el.value); });
    if (after) after();
  }

  // The clear button only appears when there is something to clear.
  Object.keys(cards).forEach(function (kind) {
    var card = cards[kind];
    if (!card.clearText) return;
    function sync() { card.clearText.hidden = card.textarea.value.trim() === ""; }
    card.textarea.addEventListener("input", sync);
    card.clearText.addEventListener("click", function () {
      card.textarea.value = "";
      keep("text:" + kind, "");
      sync();
      card.textarea.focus();
      if (card.helperMsg) card.helperMsg.hidden = true;
    });
    card.syncClear = sync;
    remember(card.textarea, "text:" + kind);
    // The helper and Surprise fill the box in code, which fires no input
    // event, so they have to say so themselves.
    card.rememberText = function () { keep("text:" + kind, card.textarea.value); };
    sync();
    // "What should they say?" is typed too, and just as annoying to lose.
    remember(card.say, "say:" + kind);

    // Their lyrics get the same treatment: a whole verse is a great deal more
    // to lose to a stray reload than a sentence is.
    if (card.lyrics) {
      function syncLyrics() {
        if (card.clearLyrics) {
          card.clearLyrics.hidden = card.lyrics.value.trim() === "";
        }
      }
      card.lyrics.addEventListener("input", syncLyrics);
      if (card.clearLyrics) {
        card.clearLyrics.addEventListener("click", function () {
          card.lyrics.value = "";
          keep("lyrics:" + kind, "");
          syncLyrics();
          card.lyrics.focus();
        });
      }
      remember(card.lyrics, "lyrics:" + kind);
      syncLyrics();
    }
  });

  // The keyboard's return key says "done" (enterkeyhint), so make it do that
  // rather than insert a newline they did not want. Shift+Return still breaks
  // a line for anyone who does.
  Object.keys(cards).forEach(function (kind) {
    var card = cards[kind];
    // Deliberately not card.lyrics: a song is many lines, and the return key
    // there means "next line", not "done".
    [card.textarea, card.say].forEach(function (box) {
      if (!box) return;
      box.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          event.target.blur();
        }
      });
    });
  });

  var video = cards.video;
  // The ✕ on "what should they say", shown only when there is something to clear.
  (function () {
    var clear = video.el.querySelector(".clear-say");
    if (!clear || !video.say) return;
    function sync() { clear.hidden = video.say.value.trim() === ""; }
    video.say.addEventListener("input", sync);
    sync();
    video.syncSay = sync;
  })();

  // First picture, last picture. Each slot holds a gallery id; the preview is
  // the server's crop so what they see is the frame LTX gets.
  var betweenBox = video.el.querySelector(".between");
  var slots = { first: null, last: null };

  function slotUrl(item, slot) {
    if (item.media === "video") {
      return slot === "first"
        ? "/api/gallery/" + encodeURIComponent(item.id) + "/last-frame?v=" + item.version
        : "/api/gallery/" + encodeURIComponent(item.id) + "/frame?at=0&v=" + item.version;
    }
    return "/api/gallery/" + encodeURIComponent(item.id) + "/preview?orientation=" +
      encodeURIComponent(video.orientation) + "&v=" + item.version;
  }

  function paintSlot(slot) {
    var box = betweenBox.querySelector('.slot[data-slot="' + slot + '"]');
    var img = box.querySelector(".slot-img");
    var item = slots[slot];
    img.hidden = !item;
    if (item) img.src = slotUrl(item, slot); else img.removeAttribute("src");
    box.querySelector(".slot-pick").textContent =
      item ? t("🖼️ Pick a different one") : t("🖼️ Pick from the gallery");
    box.querySelector(".slot-clear").hidden = !item;
    box.classList.toggle("filled", !!item);
  }

  function setSlot(slot, item) {
    slots[slot] = item;
    paintSlot(slot);
    if (video.syncHelperLabel) video.syncHelperLabel();
  }

  var sourceBox = video.el.querySelector(".source");
  var sourcePicked = sourceBox.querySelector(".source-picked");
  var sourceImg = sourcePicked.querySelector("img");
  var photoInput = sourceBox.querySelector(".photo-input");
  var photoLabel = sourceBox.querySelector(".photo-label");

  var PLACEHOLDERS = {
    t2v: t("A puppy surfing a giant wave at sunset"),
    i2v: t("It flaps its wings and flies up into the clouds"),
    flf: t("The cat walks across the room and curls up in the sunny spot"),
    story: t("A little robot looking for its lost cat in a big city")
  };

  // --- the daily warm-up ---------------------------------------------------
  // Three sums, once a calendar day. The questions and the marking are the
  // server's; this is only the friendly half. The backend answers 403 on every
  // make-something route until they are right, so reloading past the overlay
  // gets them nowhere.

  var quizBox = document.getElementById("quiz");
  var sumsForm = document.getElementById("sums");
  var quizMsg = document.getElementById("quiz-msg");
  var quizToken = "";
  var quizBusy = false;   // a submission is in flight, or its new sums are on the way

  function drawSums(questions) {
    sumsForm.innerHTML = "";
    questions.forEach(function (text, i) {
      var row = document.createElement("label");
      row.className = "sum";
      var q = document.createElement("span");
      q.className = "sum-q";
      q.textContent = text;
      var eq = document.createElement("span");
      eq.className = "sum-eq";
      eq.textContent = "=";
      var input = document.createElement("input");
      // inputmode numeric rather than type=number: the iPad keypad is what is
      // wanted, the spinner arrows are not.
      input.type = "text";
      input.inputMode = "numeric";
      input.autocomplete = "off";
      input.setAttribute("enterkeyhint", i === questions.length - 1 ? "done" : "next");
      input.addEventListener("keydown", function (e) {
        if (e.key !== "Enter") return;
        e.preventDefault();
        var next = sumsForm.querySelectorAll("input")[i + 1];
        if (next) next.focus(); else checkSums();
      });
      row.appendChild(q); row.appendChild(eq); row.appendChild(input);
      sumsForm.appendChild(row);
    });
    var first = sumsForm.querySelector("input");
    if (first) first.focus();
  }

  // The grown-up escape hatch. It lets whoever is standing at the iPad past the
  // sums for an hour; it deliberately does *not* mark them as having passed, so
  // they still owe the factory three sums today.
  var grownupBox = document.getElementById("grownup");
  var grownupPin = document.getElementById("grownup-pin");
  var grownupMsg = document.getElementById("grownup-msg");

  function grownupIn() {
    var pin = grownupPin.value.trim();
    if (!pin) return;
    var button = document.getElementById("grownup-go");
    button.disabled = true;
    grownupMsg.hidden = true;
    postJSON("/api/quiz/grownup", { pin: pin })
      .then(function () {
        grownupPin.value = "";
        quizBox.hidden = true;
        grownupBox.open = false;
        refreshAllowance();
      })
      .catch(function (err) {
        grownupMsg.textContent = err.message;
        grownupMsg.className = "grownup-msg bad";
        grownupMsg.hidden = false;
        grownupPin.value = "";
      })
      .then(function () { button.disabled = false; });
  }

  document.getElementById("grownup-go").addEventListener("click", grownupIn);
  grownupPin.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); grownupIn(); }
  });

  function quizBlurb(n) {
    var blurb = document.getElementById("quiz-blurb");
    if (!blurb) return;
    blurb.textContent = n === 1
      ? t("Get it right and the factory opens for today.")
      : t("Get all {n} right and the factory opens for today.", { n: n });
  }

  function showQuiz(data) {
    quizBlurb((data.questions || []).length || data.question_count || 3);
    quizToken = data.token || "";
    drawSums(data.questions || []);
    quizMsg.hidden = true;
    grownupMsg.hidden = true;
    grownupBox.hidden = !data.grownup;
    quizBox.hidden = false;
  }

  function checkSums() {
    // One submission at a time. The token is replaced the moment an answer
    // comes back wrong, but the new sums are not drawn for another beat - a
    // second tap in that gap would post the old, still-visible answers against
    // the new token and burn a set they never saw.
    if (quizBusy) return;
    var inputs = Array.prototype.slice.call(sumsForm.querySelectorAll("input"));
    var answers = inputs.map(function (i) { return i.value.trim(); });
    if (answers.some(function (a) { return a === ""; })) {
      quizMsg.textContent = t("Fill them all in first!");
      quizMsg.className = "quiz-msg bad";
      quizMsg.hidden = false;
      return;
    }
    quizBusy = true;
    postJSON("/api/quiz", { token: quizToken, answers: answers })
      .then(function (data) {
        if (data.passed) {
          quizMsg.textContent = t("All right! Off you go.");
          quizMsg.className = "quiz-msg good";
          quizMsg.hidden = false;
          inputs.forEach(function (i) { i.parentNode.className = "sum right"; });
          // The allowance poll hides the overlay as soon as the server stops
          // asking for sums, so it waits until they have read the message.
          setTimeout(function () {
            quizBox.hidden = true;
            quizBusy = false;
            refreshAllowance();
          }, 700);
          return;
        }
        // Any wrong answer means a whole new set. The ones they got wrong are
        // marked for a moment first, so they can see which they were before
        // they go.
        var wrong = data.wrong || [];
        inputs.forEach(function (input, i) {
          input.parentNode.className = "sum " + (wrong.indexOf(i) !== -1 ? "wrong" : "right");
        });
        quizMsg.textContent = wrong.length === 1
          ? t("So close - one of those wasn't right. Here are some new ones!")
          : t("Not quite! Here are some new ones.");
        quizMsg.className = "quiz-msg bad";
        quizMsg.hidden = false;
        quizToken = data.token || "";
        setTimeout(function () {
          drawSums(data.questions || []);
          quizMsg.hidden = false;   // drawSums does not clear it; the message stays
          quizBusy = false;
        }, 1100);
      })
      .catch(function () {
        quizMsg.textContent = t("Something went wrong. Try again!");
        quizMsg.className = "quiz-msg bad";
        quizMsg.hidden = false;
        quizBusy = false;
      });
  }

  document.getElementById("quiz-go").addEventListener("click", checkSums);

  function checkQuiz() {
    return fetch("/api/quiz").then(readJSON).then(function (data) {
      if (data.needed) showQuiz(data);
      else quizBox.hidden = true;
    }).catch(function () { /* offline: do not lock them out of a page they can see */ });
  }

  // --- their own voice over a video -------------------------------------------
  // MediaRecorder hands back whatever container Safari feels like (audio/mp4
  // on iOS, webm on Chrome); the server decodes it either way and re-encodes
  // only the audio, remuxing the video frames untouched. The original video is
  // left alone - this makes a new one.

  var voiceSheet = document.getElementById("voice");
  var voicePreview = voiceSheet.querySelector(".voice-preview");
  var voiceButton = document.getElementById("voice-record");
  var voiceLabel = voiceSheet.querySelector(".voice-label");
  var voiceTime = document.getElementById("voice-time");
  var voicePlayback = document.getElementById("voice-playback");
  var voiceActions = voiceSheet.querySelector(".voice-actions");
  var voiceStatus = voiceSheet.querySelector(".voice-status");
  var voiceFile = document.getElementById("voice-file");
  var voiceDiscard = document.getElementById("voice-discard");

  var voiceFor = null;      // the gallery item being talked over
  var recorder = null;
  var recorded = null;      // the blob
  var recordChunks = [];
  var recordStart = 0;
  var recordTimer = null;
  var MAX_RECORD_MS = 60000;

  function canRecord() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
              window.MediaRecorder);
  }

  function voiceSays(text, working) {
    voiceStatus.textContent = text;
    voiceStatus.classList.toggle("working", !!working);
    voiceStatus.hidden = !text;
  }

  function openVoice(item) {
    report("voice-open", item.id + " canRecord=" + canRecord() +
      " secure=" + window.isSecureContext + " MR=" + !!window.MediaRecorder);
    voiceFor = item;
    recorded = null;
    voiceSheet.hidden = false;
    lockPage();
    voicePreview.src = fileUrl(item);
    voiceButton.hidden = !canRecord();
    voiceButton.disabled = false;
    voiceButton.dataset.on = "0";
    voiceLabel.textContent = t("Start talking");
    voiceTime.hidden = true;
    voiceTime.textContent = "0:00";
    voicePlayback.hidden = true;
    voicePlayback.removeAttribute("src");
    voiceActions.hidden = true;
    if (voiceFile) voiceFile.value = "";
    voiceDiscard.hidden = true;
    voiceSays(canRecord() ? "" :
      t("This browser can't record here - that needs https. Pick a sound from your files below instead."));
  }

  function closeVoice(force) {
    report("voice-close", "force=" + !!force + " haveRecording=" + !!(recorded && recorded.size));
    // They recorded something and reached for Close. That was almost certainly
    // meant as "I'm finished", and throwing the recording away without a word
    // is what made this look broken the first time.
    if (!force && recorded) {
      voiceSays(t("You haven't put it on your video yet!"));
      var use = document.getElementById("voice-use");
      if (use) use.scrollIntoView({ behavior: "smooth", block: "center" });
      voiceDiscard.hidden = false;
      return;
    }
    voiceDiscard.hidden = true;
    stopRecording(true);
    voiceSheet.hidden = true;
    voicePreview.pause();
    voicePreview.removeAttribute("src");
    voicePlayback.pause();
    voicePlayback.removeAttribute("src");
    voiceFor = null;
    // The gallery or the viewer is still open behind this, and they did the
    // locking. Unlocking here would let the page scroll about underneath them.
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function tick() {
    var secs = Math.floor((Date.now() - recordStart) / 1000);
    voiceTime.textContent = Math.floor(secs / 60) + ":" + (secs % 60 < 10 ? "0" : "") + (secs % 60);
    if (Date.now() - recordStart > MAX_RECORD_MS) stopRecording();
  }

  function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function (stream) {
        var types = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", ""];
        var use = types.filter(function (t) {
          return !t || (window.MediaRecorder.isTypeSupported &&
                        window.MediaRecorder.isTypeSupported(t));
        })[0];
        report("voice-gum-ok", "chosen=" + (use || "(default)") +
          " tracks=" + stream.getTracks().length);
        // Held in a local as well as in `recorder`: onstop fires on a later
        // task, and stopRecording has nulled `recorder` by then. Referring to
        // it there threw, which lost the recording after a perfectly good
        // take - and the synchronous stub I tested with never showed it.
        var rec = use ? new MediaRecorder(stream, { mimeType: use }) : new MediaRecorder(stream);
        recorder = rec;
        recordChunks = [];
        rec.ondataavailable = function (e) {
          report("voice-data", "size=" + (e.data && e.data.size));
          if (e.data && e.data.size) recordChunks.push(e.data);
        };
        rec.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          recorded = new Blob(recordChunks, { type: rec.mimeType || use || "audio/mp4" });
          report("voice-stop", "chunks=" + recordChunks.length + " bytes=" + recorded.size +
            " type=" + recorded.type);
          voicePlayback.src = URL.createObjectURL(recorded);
          voicePlayback.hidden = false;
          voiceActions.hidden = false;
          voiceButton.hidden = true;
        };
        // A timeslice, so data arrives as they talk rather than only at the
        // end: on iOS a stop that never delivers is otherwise indetectable.
        rec.start(1000);
        report("voice-start", "state=" + rec.state + " type=" + (rec.mimeType || "?"));
        recordStart = Date.now();
        // The video plays along, so they can talk in time with it.
        voicePreview.currentTime = 0;
        voicePreview.play().catch(function () {});
        voiceButton.dataset.on = "1";
        voiceLabel.textContent = t("Stop");
        voiceTime.hidden = false;
        tick();
        recordTimer = setInterval(tick, 250);
      })
      .catch(function (err) {
        // Be specific: "it didn't work" sends a child (and a parent) looking in
        // the wrong place. The name is the only reliable part of these errors.
        var name = (err && err.name) || "";
        voiceSays(
          name === "NotAllowedError" || name === "SecurityError"
            ? t("Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.")
            : name === "NotFoundError" || name === "OverconstrainedError"
              ? t("I can't find a microphone on this device. You can pick a sound from your files below instead.")
              : t("The microphone didn't start ({why}). You can pick a sound from your files below instead.",
                  { why: name || "unknown" })
        );
      });
  }

  function stopRecording(silent) {
    clearInterval(recordTimer);
    voicePreview.pause();
    voiceButton.dataset.on = "0";
    voiceLabel.textContent = t("Start talking");
    if (recorder && recorder.state !== "inactive") {
      if (silent) recorder.onstop = null;
      recorder.stop();   // onstop runs later, on its own task
    }
    recorder = null;
  }

  voiceButton.addEventListener("click", function () {
    report("voice-button", "on=" + voiceButton.dataset.on);
    if (voiceButton.dataset.on === "1") stopRecording();
    else startRecording();
  });

  document.getElementById("voice-again").addEventListener("click", function () {
    recorded = null;
    voicePlayback.hidden = true;
    voicePlayback.removeAttribute("src");
    voiceActions.hidden = true;
    voiceSays("");
    voiceDiscard.hidden = true;
    voiceButton.hidden = !canRecord();
    voiceTime.hidden = true;
  });

  // Anything that cannot record in the page - an older iPad, a browser where
  // the microphone is blocked - can still pick a voice memo. On iOS this opens
  // Files and the recorder both.
  if (voiceFile) {
    voiceFile.addEventListener("change", function () {
      var picked = voiceFile.files && voiceFile.files[0];
      if (!picked) return;
      recorded = picked;
      voicePlayback.src = URL.createObjectURL(picked);
      voicePlayback.hidden = false;
      voiceActions.hidden = false;
      voiceButton.hidden = true;
      voiceSays("");
    });
  }

  document.getElementById("voice-use").addEventListener("click", function () {
    if (!recorded || !voiceFor) return;
    var use = document.getElementById("voice-use");
    use.disabled = true;
    voiceSays(t("Putting your voice on it..."), true);
    report("voice-use", "bytes=" + recorded.size + " type=" + (recorded.type || "?") +
      " keep=" + (document.getElementById("voice-keep") || {}).checked);
    var form = new FormData();
    form.append("audio", recorded, "voice.mp4");
    var keepBox = document.getElementById("voice-keep");
    form.append("keep", keepBox && keepBox.checked ? "1" : "0");
    fetch("/api/gallery/" + encodeURIComponent(voiceFor.id) + "/voice",
          { method: "POST", body: form })
      .then(readJSON)
      .then(function (data) {
        recorded = null;
        closeVoice(true);
        refreshMine();
        showToast(t("Your voice is on it! 🎤"), { cheer: true, ms: 4000 });
        openViewerById(data.gallery_id);
      })
      .catch(function (err) {
        report("voice-use-failed", err && err.message);
        voiceSays(err.message || GENERIC_ERROR);
      })
      .then(function () { use.disabled = false; });
  });

  // --- the things they have asked for before ----------------------------------
  // Kept on the server, not in the browser, so it follows them between the iPad
  // and anything else and survives a cleared browser. Their own words only: the
  // composed prompt with the style phrases appended is not something anyone
  // wants to read back.

  var HISTORY_BUCKET = { image: "image", video: "video", comic: "comic",
                         music: "music" };

  function paintHistory(data) {
    Object.keys(cards).forEach(function (kind) {
      var card = cards[kind];
      if (!card.history) return;
      var mine = (data[HISTORY_BUCKET[kind]] || []);
      card.history.hidden = mine.length === 0;
      card.historyList.innerHTML = "";
      mine.forEach(function (idea) {
        var row = document.createElement("div");
        row.className = "history-row";

        var item = document.createElement("button");
        item.type = "button";
        item.className = "history-item";
        item.textContent = idea;
        item.addEventListener("click", function () {
          card.textarea.value = idea;
          if (card.syncClear) card.syncClear();
          if (card.rememberText) card.rememberText();
          card.history.open = false;
          card.textarea.focus();
        });
        row.appendChild(item);

        // One tap and it is gone, with no "are you sure": this is a list of
        // things they typed, not something they made, and the worst case is
        // retyping a sentence. Arming it would be heavier than the mistake.
        var drop = document.createElement("button");
        drop.type = "button";
        drop.className = "history-drop";
        drop.textContent = "✕";
        drop.setAttribute("aria-label", t("Forget “{idea}”", { idea: idea }));
        drop.addEventListener("click", function () {
          row.remove();
          if (!card.historyList.children.length) card.history.hidden = true;
          // The row is already gone from the page, so there is nothing to
          // repaint on success - and repainting would empty the list and put
          // it back, which throws away where they had scrolled to. With thirty
          // ideas and no "are you sure", that jump is how the next tap lands
          // on the wrong one. Only a failure redraws, to put the row back.
          fetch("/api/history?kind=" + encodeURIComponent(HISTORY_BUCKET[kind]) +
                "&idea=" + encodeURIComponent(idea), { method: "DELETE" })
            .then(readJSON).catch(loadHistory);
        });
        row.appendChild(drop);

        card.historyList.appendChild(row);
      });
    });
  }

  function loadHistory() {
    return fetch("/api/history").then(readJSON).then(paintHistory).catch(function () {});
  }

  // --- characters they can keep ---------------------------------------------
  // A name and one sentence about how they look, written by the vision model
  // from a picture they already made, and repeated in later prompts. It is a
  // family resemblance rather than the same character twice - Flux cannot
  // promise more than that - but it is enough for a story to read as being
  // about one person, and their saved picture is still there to animate when
  // they want the real thing.

  var cast = [];
  var castMax = 12;

  function whoIs(id) {
    return cast.filter(function (c) { return c.id === id; })[0] || null;
  }

  function paintCast() {
    paintCastShelf();
    Object.keys(cards).forEach(function (kind) {
      var card = cards[kind];
      if (!card.cast) return;
      card.cast.hidden = cast.length === 0;
      var see = card.cast.querySelector(".cast-see");
      if (!cast.length) { card.character = ""; if (see) see.hidden = true; return; }
      if (cast.every(function (c) { return c.id !== card.character; })) card.character = "";

      card.castRow.innerHTML = "";
      var nobody = document.createElement("button");
      nobody.type = "button";
      nobody.className = "cast-chip nobody" + (card.character ? "" : " is-on");
      nobody.textContent = t("Nobody");
      nobody.addEventListener("click", function () { card.character = ""; paintCast(); });
      card.castRow.appendChild(nobody);

      cast.forEach(function (who) {
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "cast-chip" + (card.character === who.id ? " is-on" : "");
        if (who.picture_id) {
          var face = document.createElement("img");
          face.src = "/api/gallery/" + encodeURIComponent(who.picture_id) + "/thumb";
          face.alt = "";
          chip.appendChild(face);
        }
        chip.appendChild(document.createTextNode(who.name));
        chip.addEventListener("click", function () {
          card.character = card.character === who.id ? "" : who.id;
          paintCast();
        });
        card.castRow.appendChild(chip);
      });

      // Only once somebody is chosen: a button that needs a selection first is
      // worse than one that appears when the selection makes it work.
      if (see) {
        var chosenWho = whoIs(card.character);
        see.hidden = !chosenWho;
        if (chosenWho) see.textContent = t("📄 Everything with {name} in it", { name: chosenWho.name });
      }
    });
  }

  // The cast on the Gallery page: their own saved picture as the face, their
  // name under it, and a tap opens their page. It used to be a button that
  // opened a sheet, which meant nothing on the page said who they had made.
  // Hidden with nobody in it, like any empty shelf.
  function paintCastShelf() {
    if (!castShelf) return;
    castShelf.hidden = cast.length === 0;
    castShelf.querySelector(".count").textContent =
      cast.length ? "(" + cast.length + ")" : "";
    castStrip.innerHTML = "";
    cast.forEach(function (who) {
      var tile = document.createElement("button");
      tile.type = "button";
      tile.className = "tile cast-tile";
      var face = document.createElement("img");
      face.alt = "";
      face.loading = "lazy";
      if (who.picture_id) {
        face.src = "/api/gallery/" + encodeURIComponent(who.picture_id) + "/thumb";
      }
      tile.appendChild(face);
      var name = document.createElement("span");
      name.className = "tile-name";
      name.textContent = who.name;
      tile.appendChild(name);
      tile.addEventListener("click", function () { openCastSheet(who.id); });
      castStrip.appendChild(tile);
    });
  }

  function loadCast() {
    return fetch("/api/characters").then(readJSON).then(function (data) {
      cast = data.characters || [];
      castMax = data.max || 12;
      paintCast();
    }).catch(function () {});
  }

  // Takes a gallery id rather than reading `viewing`, so this works from a
  // picture they have just made as well as from one they have gone back to. The
  // moment a picture appears is when they know whether they want to keep
  // whoever is in it; making them find it again later was a worse moment to ask.
  function makeCharacterFrom(galleryId, done) {
    if (!galleryId) return;
    if (cast.length >= (castMax || 12)) {
      showToast(t("That's {n} characters already! Say goodbye to one first, in the Gallery.",
                  { n: castMax }), { ms: 6000 });
      return;
    }
    var name = window.prompt(t("What's this character called?"), "");
    if (name === null) return;
    name = name.trim();
    if (!name) return;
    showToast(t("Having a good look at {name}...", { name: name }), { ms: 30000 });
    postJSON("/api/characters", { name: name, gallery_id: galleryId })
      .then(function (who) {
        loadCast();
        showToast(t("{name} can be in your next one! 🧑‍🎤", { name: who.name }),
                  { cheer: true, ms: 5000 });
        if (done) done(who);
      })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 5000 }); });
  }

  function makeCharacter() {
    if (!viewing || viewing.media !== "image") return;
    makeCharacterFrom(viewing.id);
  }

  // --- one toast, two jobs -------------------------------------------------
  // "Deleted - undo?" and "that's your 50th picture!". Both are a line at the
  // bottom that goes away on its own; there is no reason for two of them.

  var toast = document.getElementById("toast");
  var toastText = document.getElementById("toast-text");
  var toastDo = document.getElementById("toast-do");
  var toastBin = document.getElementById("toast-bin");
  var toastTimer = null;

  function showToast(text, opts) {
    opts = opts || {};
    clearTimeout(toastTimer);
    toastText.textContent = text;
    toast.classList.toggle("cheer", !!opts.cheer);
    if (opts.action) {
      toastDo.textContent = opts.action;
      toastDo.hidden = false;
      toastDo.onclick = function () {
        hideToast();
        opts.onAction();
      };
    } else {
      toastDo.hidden = true;
      toastDo.onclick = null;
    }
    // A delete beside "Show me", for the things they start from their gallery -
    // a smoothed clip, a huge picture, a sticker, a changed picture. None of
    // those has a card to draw a result into, so this line is the only place
    // they are looking when one lands, and going to find it in the Gallery is a
    // long way round to bin something they can already see they do not want.
    if (armed === toastBin) disarm();
    if (opts.bin && opts.bin.length) {
      toastBin.textContent = t("🗑️ Delete");
      toastBin.hidden = false;
      toastBin.onclick = function () {
        // Hold the line open while it is asking. A half-asked question that
        // slides away under their finger is worse than no question at all.
        clearTimeout(toastTimer);
        if (!arm(toastBin, t("Really delete?"))) return;
        disarm();
        toastBin.hidden = true;
        binThem(opts.bin)
          .then(function () {
            offerUndo(opts.bin, function () { showToast(text, opts); return true; });
          })
          .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 8000 }); });
      };
    } else {
      toastBin.hidden = true;
      toastBin.onclick = null;
    }
    toast.hidden = false;
    toastTimer = setTimeout(hideToast, opts.ms || 6000);
  }

  function hideToast() {
    clearTimeout(toastTimer);
    if (armed === toastBin) disarm();
    toast.hidden = true;
    toastDo.onclick = null;
    toastBin.onclick = null;
  }

  // Deleting moves to the trash, so undo is just putting it back. The offer
  // matters more than the mechanism: they should not have to know there is a
  // trash to feel safe tapping delete.
  // `back` puts what they deleted back where they were looking at it - the result
  // on the card, or the line that said it was ready. Returning true from it
  // means it has said so itself, and the "Put back!" line would only paint
  // over what it has just put up.
  function offerUndo(ids, back) {
    var many = ids.length > 1;
    showToast(many ? t("{n} things deleted", { n: ids.length }) : t("Deleted"), {
      action: t("Undo"),
      onAction: function () {
        Promise.all(ids.map(function (id) {
          return fetch("/api/gallery/trash/" + encodeURIComponent(id) + "/restore",
                       { method: "POST" });
        })).then(function () {
          refreshMine();
          if (back && back()) return;
          showToast(many ? t("All put back!") : t("Put back!"), { ms: 2500 });
        }).catch(function () {});
      },
    });
  }

  // One trip to the trash, wherever the tap came from: the delete under a
  // finished result, the one on each of four, and "Keep this one" binning the
  // three they did not choose all go through here. Nothing in it touches the
  // day's allowance, on purpose - `usage_today` counts the trash as well, so
  // deleting something never gives them a picture back.
  function binThem(ids) {
    var going = ids.length === 1
      ? fetch("/api/gallery/" + encodeURIComponent(ids[0]), { method: "DELETE" }).then(readJSON)
      : postJSON("/api/gallery/delete", { ids: ids });
    return going.then(function (data) { refreshMine(); return data; });
  }

  var MILESTONE_WORD = { image: "picture", video: "video", comic: "comic",
                         movie: "film" };

  function cheerMilestone(m) {
    if (!m) return;
    // Keyed on the kind rather than built from the server's plural word: the
    // English "first picture" from "pictures" is a chopped "s", and French
    // has no such trick.
    var word = MILESTONE_WORD[m.kind] || "picture";
    var text = m.count === 1
      ? t("Your very first " + word + "! 🎉")
      : t("That's {n} " + word + "s! 🎉", { n: m.count });
    showToast(text, { cheer: true, ms: 7000 });
    confetti(70);
  }

  // --- how many are left today --------------------------------------------
  // The parent page can cap pictures and videos per day. When a cap is set they
  // gets a countdown on the card rather than a refusal out of nowhere at the
  // end; with no cap set, nothing is shown at all. The server enforces it
  // either way (409), this is only so the number is never a surprise.

  var allowanceState = { image: null, video: null };
  var paused = false;
  var pausedBox = document.getElementById("paused");
  var pausedWhen = document.getElementById("paused-when");

  // Which allowance a card spends. A comic is several pictures, so it comes
  // out of the picture limit - and the comic card has to say so, or the
  // countdown would sit on the Picture tab while the Comic tab quietly ran
  // them out of pictures.
  // A banner is a picture, in an unusual shape. It spends one like any other.
  var SPENDS = { image: "image", video: "video", comic: "image", banner: "image",
                 music: "music" };

  function noneLeft(card) {
    var a = allowanceState[spendsOf(card)];
    return !!(a && a.left !== null && a.left !== undefined && a.left <= 0);
  }

  // Which allowance one tap on this card comes out of. Fixed per card for
  // five of the six; the Story card borrows a different maker at every step,
  // so what it spends is a property of where they are in the flow. `story` is
  // declared much further down - this can be asked before that line has run,
  // and a card with no step yet spends nothing.
  var STORY_SPENDS = { picture: "image", film: "video", song: "music" };

  function spendsOf(card) {
    if (card.kind === "story") {
      return (typeof story !== "undefined" && story) ? STORY_SPENDS[story.step] : null;
    }
    return SPENDS[card.kind];
  }

  // How many one tap on this card will actually use.
  function costOf(card) {
    if (card.kind === "story") return story && story.step === "film" ? (card.parts || 2) : 1;
    if (card.kind === "comic") return card.panels || 4;
    if (card.kind === "video" && currentMode() === "story") return card.parts || 3;
    if (card.kind === "image") return card.count || 1;
    return 1;
  }

  function renderAllowance() {
    Object.keys(cards).forEach(function (kind) {
      var card = cards[kind];
      if (!card.allowance) return;
      var spends = spendsOf(card);
      var a = allowanceState[spends];
      if (!a || a.left === null || a.left === undefined) {
        card.allowance.hidden = true;
        card.allowance.classList.remove("none-left");
        return;
      }
      var thing = spends === "image" ? "picture" : spends === "music" ? "song" : "video";
      var want = costOf(card);
      var out;
      // A sentence per kind and per shape rather than a noun and an "s"
      // dropped into one: French agrees the number with the noun and puts it
      // somewhere else in the sentence.
      if (a.left <= 0) {
        out = t("🌙 That's all the " + thing + "s for today. See you tomorrow!");
      } else if (want > a.left) {
        // Asking for more than is left is not refused, it is trimmed - so say
        // what will actually happen rather than letting them find out after.
        out = a.left === 1
          ? t("✨ 1 " + thing + " left today, so that's how many you'll get.")
          : t("✨ {n} " + thing + "s left today, so that's how many you'll get.",
              { n: a.left });
      } else if (a.left === 1) {
        out = t("✨ One more " + thing + " today - make it a good one!");
      } else {
        out = t("✨ {n} more " + thing + "s today", { n: a.left });
      }
      card.allowance.textContent = out;
      card.allowance.classList.toggle("none-left", a.left <= 0);
      card.allowance.hidden = false;
    });
    // Re-apply the button state: running out is as good a reason to be
    // disabled as another job being in flight.
    setBusy(activeCard);
  }

  // "It closes at 6pm - about 20 minutes left." Shown only inside the last
  // half hour, because a warning that is always on the page is not a warning.
  var closingBox = document.getElementById("closing");
  var closingText = document.getElementById("closing-text");

  function showClosingSoon(data) {
    if (!closingBox) return;
    var mins = data.closes_in;
    if (mins === null || mins === undefined || !data.closes_at) {
      closingBox.hidden = true;
      return;
    }
    closingText.textContent = mins <= 1
      ? t("The factory closes at {at} - any minute now!", { at: data.closes_at })
      : t("closes-in", { at: data.closes_at, mins: mins });
    closingBox.hidden = false;
  }

  function refreshAllowance() {
    return fetch("/api/allowance").then(readJSON).then(function (data) {
      paused = !!data.paused;
      if (pausedBox) pausedBox.hidden = !paused;
      // A timetable knows when it opens, so the sign says so. A grown-up who
      // shut it by hand has told us nothing except that it is shut, and
      // "back soon" is the only honest thing left to put there.
      if (pausedWhen) pausedWhen.textContent = data.closed_sub || t("Back soon!");
      showClosingSoon(data);
      // Closing the factory while they are mid-sum takes the sums away; the
      // "back soon" sign is the only thing worth showing then.
      if (paused) quizBox.hidden = true;
      // Midnight while the page sits open, or the factory reopening: due again.
      else if (data.quiz_needed) { if (quizBox.hidden) checkQuiz(); }
      // No longer owed - they passed on another tab, or a parent just waved them
      // through. Taking the overlay down is this poll's job; nothing else does
      // it, and without this "let them skip them today" never reaches their iPad.
      else if (!quizBusy) quizBox.hidden = true;
      allowanceState = data.allowance || { image: null, video: null };
      renderAllowance();
    }).catch(function () { /* a blip should not lock them out */ });
  }

  // --- "about two minutes" --------------------------------------------------
  // Answered by the server from what this machine has actually done, so the
  // number is right on a slow card as well as a fast one. Before the first
  // render of a given shape there is nothing honest to say, so it says that.

  function niceTime(seconds) {
    if (seconds < 45) {
      return t("about {n} seconds", { n: Math.round(seconds / 5) * 5 });
    }
    var mins = seconds / 60;
    if (mins < 1.4) return t("about a minute");
    if (mins < 10) {
      var half = Math.round(mins * 2) / 2;
      return t("about {n} minutes",
               { n: half % 1 ? half.toFixed(1).replace(".5", "\u00bd") : half });
    }
    return t("about {n} minutes", { n: Math.round(mins) });
  }

  function etaQuery(card) {
    var kind = card.kind;
    var q = { orientation: card.orientation, count: card.count || 1 };
    if (card.kind === "story") {
      if (!story || story.step === "idea" || story.step === "together") return "";
      kind = story.step === "picture" ? "image"
        : story.step === "film" ? "story" : "music";
      if (kind === "story") { q.parts = card.parts || 2; q.duration = card.seconds; }
      if (kind === "music") q.duration = card.seconds;
      q.kind = kind;
      return Object.keys(q).map(function (k) {
        return encodeURIComponent(k) + "=" + encodeURIComponent(q[k]);
      }).join("&");
    }
    if (card.kind === "video") {
      kind = currentMode();
      if (kind === "story") { q.parts = card.parts || 3; kind = "story"; }
      q.duration = card.seconds;
      q.quality = card.quality || "normal";
    } else if (card.kind === "comic") {
      q.count = card.panels || 4;
      kind = "panel";
    }
    q.kind = kind;
    return Object.keys(q).map(function (k) {
      return encodeURIComponent(k) + "=" + encodeURIComponent(q[k]);
    }).join("&");
  }

  var etaTimers = {};

  function refreshEta(card) {
    if (!card || !card.etaNote) return;
    // The Story card's steps that spend nothing have nothing to estimate.
    var query = etaQuery(card);
    if (!query) { card.etaNote.hidden = true; return; }
    clearTimeout(etaTimers[card.kind]);
    // Debounced: dragging the length slider would otherwise be one request a
    // pixel, and the answer only changes at whole seconds anyway.
    etaTimers[card.kind] = setTimeout(function () {
      fetch("/api/estimate?" + query).then(readJSON).then(function (data) {
        if (!data || !data.seconds) {
          card.etaNote.textContent =
            t("⏱️ I haven't made one of these yet — I'll time this one.");
          card.etaNote.hidden = false;
          return;
        }
        card.etaNote.textContent = t(
          data.confidence === "measured"
            ? "⏱️ Takes {time} on this computer."
            : "⏱️ Probably takes {time}.",
          { time: niceTime(data.seconds) });
        card.etaNote.hidden = false;
      }).catch(function () { card.etaNote.hidden = true; });
    }, 180);
  }

  function refreshAllEtas() {
    Object.keys(cards).forEach(function (k) { refreshEta(cards[k]); });
  }

  // --- busy state ---------------------------------------------------------
  // One job at a time. The backend enforces it too (409); this just means they
  // never gets to tap something that would be refused.

  var activeCard = null;

  // The tab title carries the progress too, so a glance at the tab bar - or
  // the home screen app switcher - says how far along it is.
  var BASE_TITLE = document.title;
  var titleTimer = null;
  function setTitle(text) {
    clearTimeout(titleTimer);
    document.title = text ? text + " · " + BASE_TITLE : BASE_TITLE;
  }
  function flashTitle(text) {
    setTitle(text);
    titleTimer = setTimeout(function () { setTitle(""); }, 8000);
  }

  function setBusy(card) {
    activeCard = card;
    Object.keys(cards).forEach(function (kind) {
      var c = cards[kind];
      c.button.disabled = card !== null || noneLeft(c);
      if (c.helper) c.helper.disabled = card !== null;
      if (c.surprise) c.surprise.disabled = card !== null;
      // Clearing the card mid-render would throw away the words that made the
      // thing they are watching, and would not stop it. Stop does that.
      if (c.reset) c.reset.disabled = card !== null;
      // Same for deleting what is still on the card from last time: it is a
      // decision about a finished thing, and mid-render is not the moment.
      // The bin on one of four is the exception and is left alone: those
      // tiles appear one at a time while the rest are still being drawn, and
      // each one is a finished picture the moment it is there.
      if (c.result) {
        Array.prototype.forEach.call(c.result.querySelectorAll(".bin"),
          function (b) { b.disabled = card !== null; });
      }
      c.stop.hidden = c !== card;
    });
    if (photoInput) photoInput.disabled = card !== null;
    markWorkingTab();
  }

  function setIdle() {
    setBusy(null);
  }

  // --- a ding when it is done ---------------------------------------------
  // Videos take minutes and they will wander off. Web Audio needs a user
  // gesture before it will make a sound, so the context is created on the tap
  // that starts a job and only played later.
  var audio = null;
  function armDing() {
    try {
      if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
    } catch (e) { audio = null; }
  }
  function ding() {
    if (!audio) return;
    try {
      var now = audio.currentTime;
      [[660, 0], [880, 0.16], [1320, 0.32]].forEach(function (note) {
        var osc = audio.createOscillator();
        var gain = audio.createGain();
        osc.type = "sine";
        osc.frequency.value = note[0];
        gain.gain.setValueAtTime(0.0001, now + note[1]);
        gain.gain.exponentialRampToValueAtTime(0.25, now + note[1] + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + note[1] + 0.45);
        osc.connect(gain).connect(audio.destination);
        osc.start(now + note[1]);
        osc.stop(now + note[1] + 0.5);
      });
    } catch (e) { /* no sound is not a problem */ }
  }

  // --- sharing --------------------------------------------------------------
  // iOS Safari can hand a file to AirDrop, Messages or Photos through the
  // share sheet, which beats "Save" landing in the Files app.
  var canShareFiles = false;
  try {
    canShareFiles = !!(navigator.share && navigator.canShare &&
      navigator.canShare({ files: [new File([new Blob(["x"])], "x.png", { type: "image/png" })] }));
  } catch (e) { canShareFiles = false; }

  function shareUrl(url, filename, button) {
    var label = button ? button.textContent : "";
    if (button) { button.disabled = true; button.textContent = t("Getting it ready..."); }
    return fetch(url)
      .then(function (r) { if (!r.ok) throw new Error(GENERIC_ERROR); return r.blob(); })
      .then(function (blob) {
        var file = new File([blob], filename, { type: blob.type });
        return navigator.share({ files: [file], title: appTitle });
      })
      .catch(function () { /* they cancelled the share sheet, or it failed - either is fine */ })
      .then(function () { if (button) { button.disabled = false; button.textContent = label; } });
  }

  // --- small helpers ------------------------------------------------------

  function showStatus(card, text, isBad) {
    card.status.hidden = false;
    card.msg.textContent = text;
    card.msg.classList.toggle("bad", !!isBad);
  }

  // A film is their one sentence broken into parts by the model, each carrying on
  // from the last. They used to wait four minutes with no idea what it had
  // decided; the plan appears as soon as it exists, with the part being filmed
  // now marked, so the wait is readable and a story that came out wrong is
  // obvious before the end rather than after it.
  function showPlan(card, job) {
    var beats = (job.extra && job.extra.beats) || [];
    if (!beats.length) {
      if (card.plan) card.plan.hidden = true;
      return;
    }
    if (!card.plan) {
      card.plan = document.createElement("ol");
      card.plan.className = "film-plan";
      card.status.appendChild(card.plan);
    }
    // Which part is being filmed, from the message the job writes ("Part 2 of
    // 3 filmed..."), so there is one source of truth for the count.
    var done = 0;
    var m = /(\d+)\s+of\s+\d+/.exec(job.message || "");
    if (m) done = parseInt(m[1], 10) || 0;

    if (card.plan.children.length !== beats.length) {
      card.plan.innerHTML = "";
      beats.forEach(function (beat) {
        var li = document.createElement("li");
        li.textContent = beat.scene || "";
        if (beat.says) {
          var says = document.createElement("span");
          says.className = "plan-says";
          says.textContent = "\u201c" + beat.says + "\u201d";
          li.appendChild(says);
        }
        card.plan.appendChild(li);
      });
    }
    Array.prototype.forEach.call(card.plan.children, function (li, i) {
      li.classList.toggle("is-done", i < done);
      li.classList.toggle("is-now", i === done);
    });
    card.plan.hidden = false;
  }

  function setProgress(card, fraction) {
    if (fraction > 0) {
      card.bar.classList.remove("waiting");
      var percent = Math.round(fraction * 100);
      card.fill.style.width = percent + "%";
      card.pct.textContent = percent + "%";
      if (fraction < 1) setTitle(percent + "%");
    } else {
      card.bar.classList.add("waiting");
      card.pct.textContent = "";
    }
  }

  // 95 -> "1:35", 40 -> "40 seconds"
  function clock(total) {
    var secs = Math.max(0, Math.round(total));
    if (secs < 60) {
      return secs === 1 ? t("{n} second", { n: secs }) : t("{n} secs", { n: secs });
    }
    var m = Math.floor(secs / 60);
    var s = secs % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  // "GPU 98% · 14.1 of 16.3 GB · CPU 12%": proof the machine is working,
  // which matters most in the long flat stretches of a video render.
  function showSystem(card, job) {
    var sy = job.system;
    if (!card.sys || !sy) return;
    // Each figure is its own span, and the " · " between them comes from CSS,
    // so dropping the VRAM one on a narrow screen does not leave its separator
    // stranded behind.
    var bits = [];
    if (sy.gpu_pct !== null && sy.gpu_pct !== undefined) {
      bits.push("<span>GPU <b class='" + (sy.gpu_pct >= 50 ? "hot" : "") + "'>" + sy.gpu_pct + "%</b></span>");
    }
    if (sy.vram_used_mb && sy.vram_total_mb) {
      bits.push("<span class='vram'>" +
        t("{used} of {total} GB", { used: (sy.vram_used_mb / 1000).toFixed(1),
                                    total: (sy.vram_total_mb / 1000).toFixed(1) }) +
        "</span>");
    }
    if (sy.cpu_pct !== null && sy.cpu_pct !== undefined) {
      bits.push("<span>CPU <b>" + Math.round(sy.cpu_pct) + "%</b></span>");
    }
    card.sys.innerHTML = bits.join("");
    card.sys.hidden = bits.length === 0;
  }

  function showTiming(card, job) {
    var parts = [];
    if (job.elapsed > 2) parts.push(t("{time} so far", { time: clock(job.elapsed) }));
    if (job.eta !== null && job.eta !== undefined && job.eta > 5) {
      parts.push(t("about {time} to go", { time: clock(job.eta) }));
    }
    card.timing.textContent = parts.join(" · ");
    card.timing.hidden = parts.length === 0;
  }

  function clearResult(card) {
    card.result.hidden = true;
    card.result.innerHTML = "";
    card.choices = null;
  }

  function fail(card, text) {
    clearTimeout(card.timer);
    card.status.hidden = false;
    card.timing.hidden = true;
    if (card.sys) card.sys.hidden = true;
    card.bar.classList.remove("waiting");
    card.fill.style.width = "0%";
    card.pct.textContent = "";
    showStatus(card, text || GENERIC_ERROR, true);
    card.jobId = null;
    setIdle();
    hideNow();
    setTitle("");
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(readJSON);
  }

  function readJSON(r) {
    return r.json().catch(function () { return {}; }).then(function (data) {
      if (!r.ok) throw new Error(data.detail || GENERIC_ERROR);
      return data;
    });
  }

  // --- video card: mode and length ----------------------------------------

  function currentMode() {
    return video.el.dataset.mode;
  }

  function setMode(mode) {
    video.el.dataset.mode = mode;
    // A film of three parts and one clip of the same length are minutes apart.
    refreshEta(video);
    Array.prototype.forEach.call(video.modes, function (btn) {
      var on = btn.dataset.mode === mode;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
    sourceBox.hidden = mode !== "i2v";
    if (betweenBox) betweenBox.hidden = mode !== "flf";
    if (video.partsBox) video.partsBox.hidden = mode !== "story";
    // A film is joined from parts; a sound goes on one clip. Not offered there.
    if (video.effectRow) video.effectRow.hidden = mode === "story";
    applyModeToDropdowns();
    video.textarea.placeholder = PLACEHOLDERS[mode];
    video.button.textContent = mode === "i2v" ? t("Animate it")
      : mode === "story" ? t("Make my film") : t("Make my video");
    syncHelperLabel();
    renderAllowance();
  }

  function syncHelperLabel() {
    if (!video.helper) return;
    var looking = currentMode() === "i2v" && source;
    video.helper.textContent = looking
      ? t("👀 Look at my picture and help me write it") : t("✨ Help me write it");
  }

  Array.prototype.forEach.call(video.modes, function (btn) {
    btn.addEventListener("click", function () { setMode(btn.dataset.mode); });
  });

  function setOrientation(card, name) {
    card.orientation = name;
    card.el.dataset.orientation = name;
    Array.prototype.forEach.call(card.orients, function (btn) {
      var on = btn.dataset.orientation === name;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  // Sharper costs memory in proportion to pixels times frames, and the long
  // end already sits near the top of the card. So sharper shortens the slider
  // rather than letting them find out what running out looks like; the server
  // clamps the same way whatever the page sends.
  //
  // Filled in from /api/styles, because the real numbers are a property of the
  // machine and live in .env. These are only what to use before it answers.
  var QUALITY_MAX = { quick: 15, normal: 15, sharp: 10 };

  // [min, default, max] per card, as the server last reported them. "Start
  // again" needs the same numbers the sliders were built from, and they are
  // not in the markup any more.
  var LENGTHS = { video: [5, 5, 15], music: [10, 30, 120] };

  // Apply a [min, default, max] triple from the server to a card's slider.
  // Their current value is kept if it still fits, so a reload mid-thought does
  // not quietly move the handle.
  function setLengthRange(card, range) {
    if (!card || !card.length || !range || range.length !== 3) return;
    var low = range[0], preset = range[1], high = range[2];
    // **Read their value first.** Setting `max` on a range input clamps the
    // value there and then, so asking afterwards whether it still fits always
    // says yes - it fits because the browser just made it. That did not
    // matter while a card's bounds only ever arrived once; the sound chips
    // change them on a tap, and a 30-second song became a 20-second jingle
    // pinned to its ceiling instead of the 12 the kind asks for.
    var now = parseInt(card.length.value, 10);
    card.length.min = low;
    card.length.max = high;
    var ends = card.el.querySelectorAll(".slider-end");
    if (ends.length >= 2) {
      ends[0].textContent = low + "s";
      ends[1].textContent = high + "s";
    }
    setSeconds(card, now >= low && now <= high ? now : preset);
  }

  function setQuality(card, quality) {
    card.quality = quality;
    card.el.dataset.quality = quality;
    if (card.qualMax) card.qualMax.textContent = QUALITY_MAX.sharp;
    if (card.length) {
      card.length.max = QUALITY_MAX[quality] || 15;
      var end = card.el.querySelector(".slider-end:nth-of-type(2)");
      if (end) end.textContent = card.length.max + "s";
      setSeconds(card, card.seconds);
    }
  }

  function setSeconds(card, seconds) {
    if (!card.length) return;
    var n = Math.max(+card.length.min || 5, Math.min(+card.length.max || 15, Math.round(seconds) || 5));
    card.seconds = n;
    card.length.value = n;
    card.length.setAttribute("aria-valuetext", t("{n} seconds", { n: n }));
    if (card.lengthOut) card.lengthOut.textContent = n;
    refreshEta(card);
  }

  function wireChoice(group, onPick) {
    Array.prototype.forEach.call(group, function (btn) {
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call(group, function (other) {
          var on = other === btn;
          other.classList.toggle("is-on", on);
          other.setAttribute("aria-checked", on ? "true" : "false");
        });
        onPick(btn);
      });
    });
  }

  Object.keys(cards).forEach(function (kind) {
    var card = cards[kind];
    if (card.length) {
      // "input" fires as the thumb moves, so the number tracks their finger.
      card.length.addEventListener("input", function () { setSeconds(card, card.length.value); });
      setSeconds(card, card.length.value);
    }
    wireChoice(card.panelCounts, function (btn) {
      card.panels = parseInt(btn.dataset.panels, 10) || 4;
      renderAllowance();
      refreshEta(card);
    });
    wireChoice(card.partPicks, function (btn) {
      card.parts = parseInt(btn.dataset.parts, 10) || 3;
      renderAllowance();
      refreshEta(card);
    });
    wireChoice(card.kindPicks, function (btn) {
      setCutout(card, btn.dataset.cutout === "1");
    });
    wireChoice(card.singPicks, function (btn) {
      setSinging(card, btn.dataset.singing === "1");
    });
    wireChoice(card.qualPicks, function (btn) {
      setQuality(card, btn.dataset.quality || "normal");
      refreshEta(card);
    });
    wireChoice(card.counts, function (btn) {
      card.count = parseInt(btn.dataset.count, 10) || 1;
      renderAllowance();
      refreshEta(card);
      card.button.textContent = card.count > 1
        ? t("Make {n} pictures", { n: card.count }) : t("Make my picture");
    });
    wireChoice(card.orients, function (btn) {
      card.orientation = btn.dataset.orientation || "landscape";
      card.el.dataset.orientation = card.orientation;
      // The thumbnail is cropped server-side; re-request it so what they see
      // matches the shape they just chose.
      if (card === video && source && source.galleryId) {
        sourceImg.src = "/api/gallery/" + encodeURIComponent(source.galleryId) +
          "/preview?orientation=" + encodeURIComponent(card.orientation) + "&t=" + Date.now();
      }
      if (card === video) { paintSlot("first"); paintSlot("last"); }
      refreshEta(card);
    });
  });

  // Once, on load, so every card has a number before they touch anything.
  refreshAllEtas();

  // --- style / place / lighting / mood dropdowns ---------------------------
  // Built from /api/styles so the wording lives in one place on the server.

  // Every dropdown alphabetical, here rather than on the server, so the
  // order follows whatever language the labels are shown in. A "none" choice
  // ("No music") stays first: it is the off switch, not an entry under N.
  // localeCompare so accented labels sort where a reader expects them.
  function byLabel(choices) {
    return choices.slice().sort(function (a, b) {
      if (a.id === "none") return -1;
      if (b.id === "none") return 1;
      return String(a.label).localeCompare(String(b.label), I18N.lang, { sensitivity: "base" });
    });
  }

  function buildDropdowns(card, groups) {
    if (!card.dropdowns) return;
    card.dropdowns.innerHTML = "";

    groups.forEach(function (group) {
      var wrap = document.createElement("label");
      var caption = document.createElement("span");
      caption.textContent = group.label;
      wrap.appendChild(caption);

      var select = document.createElement("select");
      select.dataset.group = group.id;
      select.dataset.default = group.default || "";
      // Dropdowns that mean nothing with nobody singing, so setSinging can
      // find them without knowing their names.
      if (group.voice_only) select.dataset.voiceOnly = "1";

      var blank = document.createElement("option");
      blank.value = "";
      // "Any" is right for a mood and wrong for a language: there is no such
      // thing as a song in no language, only one in whichever they wrote.
      blank.textContent = group.blank || t("Any");
      select.appendChild(blank);

      byLabel(group.choices).forEach(function (choice) {
        var option = document.createElement("option");
        option.value = choice.id;
        option.textContent = choice.label;
        select.appendChild(option);
      });

      select.addEventListener("change", function () { markSelect(select); });
      select.value = select.dataset.default;
      markSelect(select);

      wrap.appendChild(select);
      wrap.dataset.modes = (group.modes || ["t2v", "i2v"]).join(" ");
      card.dropdowns.appendChild(wrap);
    });
  }

  // Highlight a dropdown only when it is away from where it starts, so a
  // default of "None" for music does not light up as if they had chosen it.
  function markSelect(select) {
    select.classList.toggle("is-set", select.value !== (select.dataset.default || ""));
  }

  function resetSelect(select) {
    select.value = select.dataset.default || "";
    markSelect(select);
  }

  function chosenStyles(card) {
    var picked = {};
    if (!card.dropdowns) return picked;
    Array.prototype.forEach.call(card.dropdowns.querySelectorAll("select"), function (sel) {
      if (sel.value) picked[sel.dataset.group] = sel.value;
    });
    return picked;
  }

  function resetStyles(card) {
    if (!card.dropdowns) return;
    Array.prototype.forEach.call(card.dropdowns.querySelectorAll("select"), resetSelect);
  }

  // The sound-effect dropdown on the video card, filled from the same list the
  // add-a-sound sheet uses.
  if (video.effectPick) {
    fetch("/api/sounds").then(readJSON).then(function (data) {
      byLabel(data.sounds || []).forEach(function (e) {
        var o = document.createElement("option");
        o.value = e.id;
        o.textContent = e.emoji + " " + e.label;
        video.effectPick.appendChild(o);
      });
    }).catch(function () { if (video.effectRow) video.effectRow.hidden = true; });
    video.effectPick.addEventListener("change", function () {
      video.effectPick.classList.toggle("is-set", !!video.effectPick.value);
      // The hidden attribute is on the <label> around it, not the select.
      if (video.effectWhen) video.effectWhen.closest("label").hidden = !video.effectPick.value;
    });
  }

  fetch("/api/styles")
    .then(readJSON)
    .then(function (data) {
      buildDropdowns(cards.image, data.image || []);
      if (cards.story) {
        // The opening picture is a picture, so it gets the picture's looks -
        // and the film is made from that picture, so one set of choices
        // decides how the whole story looks.
        buildDropdowns(cards.story, data.image || []);
        setLengthRange(cards.story, data.video_seconds);
      }
      buildDropdowns(cards.video, data.video || []);
      if (cards.comic) buildDropdowns(cards.comic, data.comic || []);
      if (data.quality_max) QUALITY_MAX = data.quality_max;
      if (data.video_seconds) LENGTHS.video = data.video_seconds;
      if (data.music_seconds) LENGTHS.music = data.music_seconds;
      setLengthRange(cards.video, data.video_seconds);
      setLengthRange(cards.music, data.music_seconds);
      // setQuality reads QUALITY_MAX, so the video slider has to be told again
      // now that both it and the caps are the server's numbers.
      if (cards.video) setQuality(cards.video, cards.video.quality || "normal");
      if (cards.music) buildDropdowns(cards.music, data.music || []);
      // After the dropdowns, not before: choosing a kind hides the rows it
      // has no use for, and it cannot hide what does not exist yet. This also
      // re-applies the length bounds, so it has to come after
      // setLengthRange(cards.music, ...) above rather than be undone by it.
      if (cards.music) buildSoundKinds(cards.music, data.music_kinds || []);
      // A tab that answers "switched off" or "not set up" on every tap is
      // worse than no tab, so this is where they come and go.
      applyModules(data.modules, data.story_steps);
      // The banner is a picture, so it gets the picture's looks.
      if (cards.banner) buildDropdowns(cards.banner, data.image || []);
      // ...and the "Turn it into..." row, which is a list of choices like any
      // other and comes from the same answer rather than a fetch of its own.
      buildRestyleChips(data.restyles);
      applyModeToDropdowns();
      // The dropdowns arrive after the page has settled, so whatever state the
      // character picker is in has to be applied to them once they exist.
      Object.keys(cards).forEach(function (k) {
        if (cards[k].kindPicks && cards[k].kindPicks.length) {
          setCutout(cards[k], cards[k].cutout);
        }
      });
    })
    .catch(function () {
      // Not essential - the prompt box alone still works.
      Object.keys(cards).forEach(function (k) {
        var extras = cards[k].el.querySelector(".extras");
        if (extras) extras.hidden = true;
      });
    });

  // Starting from a picture, the scene and style are already decided by that
  // picture, so those dropdowns are hidden rather than left to fight it.
  // "A character" is the same idea drawn alone on a plain background, so it
  // can be cut out as a sticker and so the vision model has nothing but the
  // character to describe. Two of the dropdowns have to go with it: a place
  // and a plain background are contradictory instructions, and Flux settles
  // that by drawing the place. The server drops them too - this is only so they
  // is not looking at a dropdown that would be ignored.
  var CUTOUT_HIDES = ["scene", "lighting"];

  // With singing, the words box matters and "Who sings it" is a real choice;
  // without it, both are noise. Hidden rather than disabled - a greyed-out box
  // is still something to read and wonder about.
  function setSinging(card, on) {
    card.singing = !!on;
    if (card.wordsRow) card.wordsRow.hidden = !on;
    if (card.dropdowns) {
      Array.prototype.forEach.call(card.dropdowns.children, function (wrap) {
        var select = wrap.querySelector("select");
        if (!select || select.dataset.voiceOnly !== "1") return;
        wrap.hidden = !on;
      });
    }
    if (card.button) card.button.textContent = on ? t("Make my song") : t("Make my music");
    refreshEta(card);
  }

  // --- what kind of sound ---------------------------------------------------
  // Three chips at the top of the music card: a song, a little tune, a
  // background hum. One model and one graph underneath all three - what
  // changes is the tag line, how long it is allowed to be, and whether
  // anything is sung. See app/music.py KINDS.

  var SOUND_GO = {
    song: "Make my song",
    jingle: "Make my tune",
    ambience: "Make my sound",
  };

  function buildSoundKinds(card, kinds) {
    if (!card || !card.soundKinds || !kinds || !kinds.length) return;
    card.soundKindList = kinds;
    card.soundKinds.innerHTML = "";
    kinds.forEach(function (kind) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sound-kind-pick";
      btn.dataset.soundKind = kind.id;
      btn.setAttribute("role", "radio");
      btn.textContent = kind.label;
      card.soundKinds.appendChild(btn);
    });
    wireChoice(card.soundKinds.querySelectorAll(".sound-kind-pick"), function (btn) {
      setSoundKind(card, btn.dataset.soundKind);
    });
    setSoundKindPicked(card, card.soundKind || "song");
  }

  function soundKindSpec(card, id) {
    var list = card.soundKindList || [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  function setSoundKind(card, id) {
    var spec = soundKindSpec(card, id);
    if (!spec) return;
    card.soundKind = spec.id;
    card.el.dataset.soundKind = spec.id;
    if (card.soundKindNote) card.soundKindNote.textContent = spec.hint || "";

    // Nothing is sung on a tune or a hum, so the whole singing question goes
    // away rather than being asked and ignored. `setSinging` still does the
    // work, so the words box and the three vocal dropdowns hide exactly as
    // they do for "Just music" - one mechanism, not two that can disagree.
    if (card.singRow) card.singRow.hidden = !spec.sings;
    setSinging(card, spec.sings);
    if (spec.sings) setSingingPicked(card, true);

    // Dropdowns this kind has no use for - a marching band behind a drone.
    var hides = spec.hides || [];
    if (card.dropdowns) {
      Array.prototype.forEach.call(card.dropdowns.children, function (wrap) {
        var select = wrap.querySelector("select");
        if (!select) return;
        if (hides.indexOf(select.dataset.group) !== -1) wrap.hidden = true;
        else if (select.dataset.voiceOnly !== "1") wrap.hidden = false;
      });
    }

    // Each kind has its own stretch of the song bounds a parent set, so the
    // slider has to move with the chip: a ninety-second jingle is not one.
    if (spec.seconds) setLengthRange(card, spec.seconds);
    if (card.button) card.button.textContent = t(SOUND_GO[spec.id] || "Make my song");
    refreshEta(card);
  }

  // The value *and* the chip. `setSoundKind` changes the setting; the chips
  // are drawn by wireChoice on a tap, so anything setting it in code - "make
  // another like this", the reset - has to put them back itself. Same shape
  // as setSingingPicked below, and for the same reason.
  function setSoundKindPicked(card, id) {
    if (!card || !card.soundKinds) return;
    if (!soundKindSpec(card, id)) id = "song";
    setSoundKind(card, id);
    pickIn(card.soundKinds.querySelectorAll(".sound-kind-pick"), "soundKind", id);
  }

  // --- start again ----------------------------------------------------------
  // One button per maker card, at the right-hand end of its title. It is not
  // an undo: it puts the card back to how it looked before they touched it,
  // which is the thing they actually want after a helper wrote something odd
  // or four settings ago stopped making sense.

  // Flip the is-on/aria-checked pair in a group of choice buttons. The setters
  // below change the *value*; the buttons are drawn by wireChoice on a tap,
  // and nothing else was putting them back.
  function pickIn(group, attribute, value) {
    Array.prototype.forEach.call(group || [], function (button) {
      var on = button.dataset[attribute] === String(value);
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  function resetCard(card) {
    if (!card) return;

    // The words, and the drafts they are mirrored into.
    if (card.textarea) {
      card.textarea.value = "";
      keep("text:" + card.kind, "");
      if (card.syncClear) card.syncClear();
    }
    if (card.say) {
      card.say.value = "";
      keep("say:" + card.kind, "");
      card.say.dispatchEvent(new Event("input"));
    }
    if (card.lyrics) {
      card.lyrics.value = "";
      keep("lyrics:" + card.kind, "");
      card.lyrics.dispatchEvent(new Event("input"));
    }

    resetStyles(card);
    setOrientation(card, "landscape");

    card.count = 1;
    pickIn(card.counts, "count", 1);
    if (card.kind === "image") card.button.textContent = t("Make my picture");

    card.panels = 4;
    pickIn(card.panelCounts, "panels", 4);
    card.parts = 3;
    pickIn(card.partPicks, "parts", 3);

    if (card.kindPicks && card.kindPicks.length) {
      setCutout(card, false);
      pickIn(card.kindPicks, "cutout", 0);
    }
    // Back to a song, which is what the card opens on - and it has to happen
    // before the length is put back below, because each kind carries its own
    // bounds and setting the kind moves the slider.
    if (card.soundKinds) setSoundKindPicked(card, "song");
    if (card.singPicks && card.singPicks.length) setSingingPicked(card, true);

    if (card.qualPicks && card.qualPicks.length) {
      setQuality(card, "normal");
      pickIn(card.qualPicks, "quality", "normal");
    }
    var range = LENGTHS[card.kind];
    if (card.length && range) setSeconds(card, range[1]);

    card.character = "";
    paintCast();

    if (card.kind === "story") storyReset(card);

    if (card === video) {
      setMode("t2v");
      pickIn(card.modes, "mode", "t2v");
      clearSource();
      setSlot("first", null);
      setSlot("last", null);
      if (card.effectPick) card.effectPick.value = "";
      if (card.effectWhen) card.effectWhen.value = "start";
      if (card.effectPick) card.effectPick.dispatchEvent(new Event("change"));
    }

    // Anything the last go left behind.
    card.tweakSeed = null;
    card.lastBody = null;
    clearResult(card);
    if (card.helperMsg) card.helperMsg.hidden = true;
    if (card.status && card.jobId === null) card.status.hidden = true;
    if (card.plan) card.plan.hidden = true;
    refreshEta(card);
  }

  // Armed only when there is something to lose. Clearing four dropdowns is not
  // worth a second tap; a verse they have just written is.
  function hasTyped(card) {
    return [card.textarea, card.say, card.lyrics].some(function (box) {
      return box && box.value.trim() !== "";
    });
  }

  function setCutout(card, on) {
    card.cutout = !!on;
    card.el.dataset.cutout = on ? "1" : "0";
    if (card.kindNote) card.kindNote.hidden = !on;
    if (!card.dropdowns) return;
    Array.prototype.forEach.call(card.dropdowns.children, function (wrap) {
      var select = wrap.querySelector("select");
      if (!select || CUTOUT_HIDES.indexOf(select.dataset.group) === -1) return;
      wrap.hidden = !!on;
      if (on) resetSelect(select);
    });
  }

  function applyModeToDropdowns() {
    if (!video.dropdowns) return;
    // A film is filmed from words, so it wants exactly the dials a plain
    // text-to-video wants - including the camera and the sound. A clip between
    // two pictures is decided by the pictures the way animating one is.
    var mode = currentMode() === "story" ? "t2v" : currentMode() === "flf" ? "i2v" : currentMode();
    Array.prototype.forEach.call(video.dropdowns.children, function (wrap) {
      var modes = (wrap.dataset.modes || "").split(" ");
      var show = modes.indexOf(mode) !== -1;
      wrap.hidden = !show;
      if (!show) {
        var sel = wrap.querySelector("select");
        if (sel) resetSelect(sel);
      }
    });
  }

  // --- the picked source picture ------------------------------------------

  function pickSource(next, previewUrl) {
    // Whatever sent them here wanted the video card, so put them on it.
    showTab("video");
    source = next;
    sourceImg.src = previewUrl;
    sourcePicked.hidden = false;
    sourceBox.classList.remove("empty");
    setMode("i2v");
    syncHelperLabel();
    video.el.scrollIntoView({ behavior: "smooth", block: "start" });
    // Safari will not open the keyboard without a direct tap, so just focus.
    setTimeout(function () { video.textarea.focus({ preventScroll: true }); }, 400);
  }

  function clearSource() {
    source = null;
    // Drop the src entirely rather than blanking it: an <img> with src="" is a
    // broken image in Safari.
    sourceImg.removeAttribute("src");
    sourcePicked.hidden = true;
    sourceBox.classList.add("empty");
    if (photoInput) photoInput.value = "";
    syncHelperLabel();
  }

  clearSource();
  setMode("t2v");
  setIdle();

  // --- photo from the iPad ------------------------------------------------

  if (photoInput) {
    photoInput.addEventListener("change", function () {
      var file = photoInput.files && photoInput.files[0];
      if (!file) return;

      var original = photoLabel.textContent;
      photoLabel.textContent = t("Sending your photo...");
      photoInput.disabled = true;

      var form = new FormData();
      form.append("photo", file);
      form.append("source", "camera");

      fetch("/api/upload", { method: "POST", body: form })
        .then(readJSON)
        .then(function (data) {
          photoLabel.textContent = original;
          photoInput.disabled = false;
          // The server worked out the shape from the photo itself - a portrait
          // snap off the iPad should animate as a portrait video without them
          // having to think about it.
          if (data.orientation) setOrientation(video, data.orientation);
          pickSource({ galleryId: data.gallery_id }, data.preview_url);
          refreshMine();   // it is in "Photos & drawings" now
        })
        .catch(function (err) {
          photoLabel.textContent = original;
          photoInput.disabled = false;
          photoInput.value = "";
          fail(video, err.message);
        });
    });
  }

  // --- a photo straight into their stuff -------------------------------------
  // The photo button on the Video card puts a picture into the video maker,
  // which is a long way round when what they want is to do *something* with a
  // photo. This one puts it in their stuff and opens it, where every button that
  // can act on a picture already lives.

  (function () {
    var start = cards.image && cards.image.el.querySelector(".photo-start .photo-input");
    if (!start) return;
    var label = cards.image.el.querySelector(".photo-start .photo-label");
    start.addEventListener("change", function () {
      var file = start.files && start.files[0];
      if (!file) return;
      var original = label.textContent;
      label.textContent = t("Sending your photo...");
      start.disabled = true;

      var form = new FormData();
      form.append("photo", file);
      form.append("source", "camera");

      fetch("/api/upload", { method: "POST", body: form })
        .then(readJSON)
        .then(function (data) {
          label.textContent = original;
          start.disabled = false;
          start.value = "";
          refreshMine();
          openViewerById(data.gallery_id);
          showToast(t("It's in your gallery! Now pick what to do with it ✨"), { ms: 7000 });
        })
        .catch(function (err) {
          label.textContent = original;
          start.disabled = false;
          start.value = "";
          fail(cards.image, err.message);
        });
    });
  })();

  // --- the idea helper ----------------------------------------------------

  function writeScript(card) {
    var idea = card.textarea.value.trim();
    // Starting from a picture, the picture is the idea: the helper looks at it
    // and writes a prompt about what is really there. Their words are optional.
    var looking = card === video && currentMode() === "i2v" && source;
    if (!idea && !looking) {
      card.helperMsg.textContent = t("Type a few words about your idea first!");
      card.helperMsg.hidden = false;
      return;
    }

    var original = card.helper.textContent;
    card.helper.disabled = true;
    card.helper.textContent = looking ? t("Looking at your picture...") : t("Thinking of ideas...");
    card.helperMsg.textContent = t("This takes a moment the first time.");
    card.helperMsg.hidden = false;

    if (card.kind === "music") { writeSong(card); return; }
    var helperKind = card.kind === "image" ? "picture"
      : card.kind === "comic" ? "comic" : "video";
    var body = { prompt: idea, duration: card.seconds, kind: helperKind };
    if (looking) {
      if (source.jobId) body.source_job_id = source.jobId;
      if (source.galleryId) body.source_gallery_id = source.galleryId;
    }

    postJSON("/api/script", body)
      .then(function (data) {
        card.textarea.value = data.prompt;
        if (card.syncClear) card.syncClear();
        if (card.rememberText) card.rememberText();
        card.helperMsg.textContent = data.description
          ? data.description + " " + t("Here's an idea for it - change anything you like.")
          : t("Here you go! Change anything you like.");
      })
      .catch(function (err) {
        card.helperMsg.textContent = err.message;
      })
      .then(function () {
        card.helper.disabled = activeCard !== null;
        card.helper.textContent = original;
        syncHelperLabel();
      });
  }

  // --- confetti ------------------------------------------------------------

  var CONFETTI_COLOURS = ["#ffd23f", "#ff6fd8", "#4fd1ff", "#56e39f", "#ff8f5e", "#c8a2ff"];

  function confetti(pieces) {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    var layer = document.createElement("div");
    layer.className = "confetti";
    layer.setAttribute("aria-hidden", "true");

    var count = pieces || 90;
    var longest = 0;
    for (var i = 0; i < count; i++) {
      var bit = document.createElement("i");
      var duration = 1.6 + Math.random() * 1.9;
      var delay = Math.random() * 0.5;
      longest = Math.max(longest, duration + delay);
      bit.style.left = (Math.random() * 100) + "%";
      bit.style.background = CONFETTI_COLOURS[i % CONFETTI_COLOURS.length];
      bit.style.animationDuration = duration + "s";
      bit.style.animationDelay = delay + "s";
      bit.style.transform = "scale(" + (0.6 + Math.random() * 0.9) + ")";
      layer.appendChild(bit);
    }

    document.body.appendChild(layer);
    setTimeout(function () { layer.remove(); }, (longest + 0.4) * 1000);
  }

  // --- surprise me ---------------------------------------------------------

  // The song helper answers with both halves at once - what it sounds like and
  // what is sung - because they have to agree, and asking twice gets two
  // models' worth of disagreement for twice the wait.
  function writeSong(card) {
    var original = card.helper.textContent;
    card.helper.disabled = true;
    card.helper.textContent = t("Writing your song...");
    card.helperMsg.textContent = t("This takes a moment the first time.");
    card.helperMsg.hidden = false;

    postJSON("/api/song-words", {
      prompt: card.textarea.value.trim(), styles: chosenStyles(card),
    })
      .then(function (data) {
        if (card.lyrics) {
          card.lyrics.value = data.lyrics || "";
          card.lyrics.dispatchEvent(new Event("input"));
        }
        // Words written means they want them sung, whatever the toggle said.
        if (data.lyrics) setSingingPicked(card, true);
        card.helperMsg.textContent =
          t("Here are some words! Change any line you like - they don't have to rhyme.");
      })
      .catch(function (err) { card.helperMsg.textContent = err.message; })
      .then(function () {
        card.helper.disabled = activeCard !== null;
        card.helper.textContent = original;
      });
  }

  // setSinging plus the buttons, for the places that change it in code.
  function setSingingPicked(card, on) {
    setSinging(card, on);
    Array.prototype.forEach.call(card.singPicks, function (b) {
      var picked = (b.dataset.singing === "1") === !!on;
      b.classList.toggle("is-on", picked);
      b.setAttribute("aria-checked", picked ? "true" : "false");
    });
  }

  function surpriseMe(card) {
    card.tweakSeed = null;
    var original = card.surprise.textContent;
    card.surprise.disabled = true;
    card.surprise.textContent = t("🎲 Thinking of something...");
    if (card.helperMsg) {
      card.helperMsg.textContent = t("Dreaming up an idea...");
      card.helperMsg.hidden = false;
    }

    var body = { kind: card.kind === "comic" ? "comic" : card.kind };
    if (card.kind === "video") body.duration = card.seconds;
    if (card.kind === "music") {
      // Which chip they are on, so the server does not spend an Ollama call
      // writing lyrics for a background hum and then throw them away.
      body.sound_kind = card.soundKind || "song";
      card.surprise.textContent = card.soundKind && card.soundKind !== "song"
        ? t("🎲 Thinking of a sound...")
        : t("🎲 Writing a song...");
    }

    postJSON("/api/surprise", body)
      .then(function (data) {
        card.textarea.value = data.prompt;
        if (card.syncClear) card.syncClear();
        if (card.rememberText) card.rememberText();
        // The look is part of the surprise, so set the dropdowns too - and
        // show them what was picked rather than changing things invisibly.
        applyStyles(card, data.styles || {});
        // A surprise song comes with words, or it is only half a surprise.
        if (card.lyrics && typeof data.lyrics === "string"
            && (!card.soundKind || card.soundKind === "song")) {
          card.lyrics.value = data.lyrics;
          card.lyrics.dispatchEvent(new Event("input"));
          setSingingPicked(card, !!data.lyrics);
        }
        confetti();
        if (card.helperMsg) {
          card.helperMsg.textContent = card.kind === "music" && data.lyrics
            ? t("Here's a whole song! Change any line you like.")
            : t("Here's an idea! Change anything you like.");
        }
      })
      .catch(function (err) {
        if (card.helperMsg) card.helperMsg.textContent = err.message;
        else fail(card, err.message);
      })
      .then(function () {
        card.surprise.disabled = activeCard !== null;
        card.surprise.textContent = original;
      });
  }

  function applyStyles(card, picked) {
    if (!card.dropdowns) return;
    var extras = card.el.querySelector(".extras");
    var any = false;
    Array.prototype.forEach.call(card.dropdowns.querySelectorAll("select"), function (sel) {
      var value = picked[sel.dataset.group] || sel.dataset.default || "";
      sel.value = value;
      markSelect(sel);
      if (sel.classList.contains("is-set")) any = true;
    });
    // Open the panel so the choices are visible, not applied behind their back.
    if (any && extras) extras.open = true;
  }

  // --- results ------------------------------------------------------------

  // The file is in the gallery the moment the job is done, and the gallery
  // route answers Range requests where the ComfyUI proxy stream cannot. iOS
  // will not show a <video> at all without ranges, which is why a finished
  // video showed up as nothing on the iPad while playing fine on a laptop.
  function resultUrl(job, extra) {
    if (job.filename) {
      return "/api/gallery/" + encodeURIComponent(job.filename) + "/file?v=" +
        encodeURIComponent(job.id) + (extra || "");
    }
    return "/api/result/" + job.id + (extra ? extra.replace("&", "?") : "");
  }

  function renderResult(card, job) {
    var src = resultUrl(job);
    // That render is a new sample, so the estimate is better than it was.
    refreshEta(card);

    // Four at once: a grid to choose from. "Keep this one" bins the rest, so
    // the gallery does not fill up with three near-misses every time. It has
    // been filling up since the first picture landed, so it is added to here
    // rather than wiped and rebuilt - a rebuild would flicker, and would put
    // back a tile they had already binned.
    var many = job.filenames && job.filenames.length > 1 &&
      job.kind !== "comic" && job.kind !== "story";
    if (!many) {
      card.choices = null;
      card.result.innerHTML = "";
    }
    if (job.kind === "comic") { renderComic(card, job); return; }
    if (job.kind === "story") { renderFilm(card, job); return; }
    if (many) { renderChoices(card, job); return; }

    var media;
    if (job.media === "audio") {
      media = songPlayer(job, src);
    } else if (job.media === "video") {
      media = document.createElement("video");
      media.src = src;
      media.controls = true;      // LTX 2.5 renders audio too - they need these
      media.playsInline = true;
      media.preload = "metadata";
      // A still of the first frame, so it is not a black box until played.
      if (job.filename) {
        media.poster = "/api/gallery/" + encodeURIComponent(job.filename) +
          "/poster?v=" + encodeURIComponent(job.id);
      }
    } else {
      media = document.createElement("img");
      media.src = src;
      media.alt = t("The picture you made");
    }
    card.result.appendChild(media);
    card.result.appendChild(singleActions(card, job, src));
    card.result.hidden = false;
  }

  // A song is a waveform with a player under it. The picture is the server's
  // drawing of the sound, so it is recognisably *that* song rather than one
  // more music-note icon in a row of identical ones.
  function songPlayer(job, src) {
    var wrap = document.createElement("div");
    wrap.className = "song";
    if (job.filename) {
      var art = document.createElement("img");
      art.className = "song-wave";
      art.alt = "";
      art.src = "/api/gallery/" + encodeURIComponent(job.filename) +
        "/poster?v=" + encodeURIComponent(job.id);
      wrap.appendChild(art);
    }
    var player = document.createElement("audio");
    player.src = src;
    player.controls = true;
    player.preload = "metadata";
    wrap.appendChild(player);
    return wrap;
  }

  // --- deleting it from where they made it ----------------------------------
  // The bin was three taps away in the Gallery: open it, find the thing, open it
  // again. Most of the time they know they do not want it the moment they see
  // it, and they are already looking at it here. It is last in the row and in
  // the viewer's red, it asks before it does anything, and it only ever moves
  // things to the trash - so the toast offers to put it back.

  function binButton(card, ids, gone) {
    var bin = document.createElement("button");
    bin.type = "button";
    bin.className = "bin";
    bin.textContent = t("🗑️ Delete");
    // Not while something is rendering, for the same reason "Start again" is
    // not: this is about the thing they made, and mid-render is not the moment.
    bin.disabled = !!activeCard;
    bin.addEventListener("click", function () {
      if (!arm(bin, t("Really delete?"))) return;
      disarm();
      bin.disabled = true;
      binThem(ids)
        .then(function () { gone(); })
        .catch(function (err) {
          bin.disabled = false;
          showToast(err.message || GENERIC_ERROR, { ms: 8000 });
        });
    });
    return bin;
  }

  // What is left once they have deleted it from here: where it went, and the one
  // button that still means anything. Everything else in that row needed the
  // file - animating it, cutting it out, putting it at the top - and a button
  // that cannot work any more is worse than no button.
  function resultGone(card) {
    card.result.innerHTML = "";
    var line = document.createElement("p");
    line.className = "msg";
    line.textContent = t("Gone - it's in the trash.");
    card.result.appendChild(line);

    // "Try again" is the usual next tap after "I don't like that one", and it
    // is the one button here that does not need the file. It only exists when
    // the card remembers what it last sent, which is what tryAgain re-posts.
    if (card.lastBody) {
      var actions = document.createElement("div");
      actions.className = "actions";
      var again = document.createElement("button");
      again.type = "button";
      again.className = "again";
      again.textContent = t("🎲 Try again");
      again.addEventListener("click", function () { tryAgain(card); });
      actions.appendChild(again);
      card.result.appendChild(actions);
    }
    card.result.hidden = false;
  }

  // The buttons under one finished thing. Also what the kept one of four gets
  // once they have chosen: before this, "four to pick from" had only "Save them
  // all", so choosing one and then trying to save it saved all four.
  function singleActions(card, job, src) {
    var actions = document.createElement("div");
    actions.className = "actions";

    var download = document.createElement("a");
    download.href = resultUrl(job, "&download=1");
    download.setAttribute("download", "");
    download.textContent = job.media === "video" ? t("⬇︎ Save video")
      : job.media === "audio" ? t("⬇︎ Save song") : t("⬇︎ Save picture");
    actions.appendChild(download);

    if (job.media === "image") {
      var animate = document.createElement("button");
      animate.type = "button";
      animate.className = "animate";
      animate.textContent = t("✨ Animate this");
      animate.addEventListener("click", function () {
        // By name, like every other button in this row. A job id names the
        // whole run, and a four-at-once run has four pictures in it - the
        // server resolves a job to the *first* of them, so the kept one of
        // four would have been animated as picture one. The job id is left
        // as the fallback for the one case with no gallery name: a file that
        // could not be filed, which /api/result can still fetch.
        pickSource(job.filename ? { galleryId: job.filename } : { jobId: job.id }, src);
      });
      actions.appendChild(animate);

      // On the Settings card this is the whole point of the picture, so it
      // leads; anywhere else it is one more thing they can do with one.
      if (job.filename) {
        var top = document.createElement("button");
        top.type = "button";
        top.className = "use-banner";
        top.textContent = t("🖼️ Put it at the top");
        top.addEventListener("click", function () {
          useAsBanner(job.filename, top);
        });
        if (card.kind === "banner") actions.insertBefore(top, actions.firstChild);
        else actions.appendChild(top);
      }

      // Only once there is somebody to be. On a one-child installation this
      // button would be a second name for "change the icon nobody can see".
      if (job.filename && me && meChip && !meChip.hidden) {
        var face = document.createElement("button");
        face.type = "button";
        face.className = "use-banner";
        face.textContent = t("👤 That one's me");
        face.addEventListener("click", function () { useAsFace(job.filename, face); });
        actions.appendChild(face);
      }

      // Needs the file to be in the gallery, which it is - job.filename is the
      // name it landed under - and only while there is room in the cast.
      // Offered here, not only in the gallery: a character picture exists to
      // be cut out, and making them go and find it again first was a step for
      // no reason.
      if (job.filename) {
        var cut = document.createElement("button");
        cut.type = "button";
        cut.className = "cut-out";
        cut.textContent = t("✂️ Turn it into a sticker");
        cut.addEventListener("click", function () {
          cut.disabled = true;
          cut.textContent = t("✂️ Cutting it out...");
          fetch("/api/gallery/" + encodeURIComponent(job.filename) + "/sticker",
                { method: "POST" })
            .then(readJSON)
            .then(function (data) {
              cut.remove();
              refreshMine();
              showToast(t("It's a sticker! ✂️"), {
                cheer: true, ms: 6000, action: t("Show me"),
                onAction: function () { openViewerById(data.gallery_id); },
                bin: [data.gallery_id],
              });
            })
            .catch(function (err) {
              cut.disabled = false;
              cut.textContent = t("✂️ Turn it into a sticker");
              showToast(err.message || GENERIC_ERROR, { ms: 8000 });
            });
        });
        actions.appendChild(cut);
      }

      if (job.filename && cast.length < (castMax || 12)) {
        var keepWho = document.createElement("button");
        keepWho.type = "button";
        keepWho.className = "keep-who";
        keepWho.textContent = t("🧑‍🎤 Save as a character");
        keepWho.addEventListener("click", function () {
          makeCharacterFrom(job.filename, function () { keepWho.remove(); });
        });
        actions.appendChild(keepWho);
      }
    } else if (job.filename) {
      // Carry on from the last frame of this video.
      var next = document.createElement("button");
      next.type = "button";
      next.className = "next";
      next.textContent = t("▶️ What happens next?");
      next.addEventListener("click", function () {
        pickSource({ galleryId: job.filename },
          "/api/gallery/" + encodeURIComponent(job.filename) + "/last-frame?v=" + job.id);
      });
      actions.appendChild(next);
    }

    var again = document.createElement("button");
    again.type = "button";
    again.className = "again";
    again.textContent = t("🎲 Try again");
    again.addEventListener("click", function () { tryAgain(card); });
    actions.appendChild(again);

    if (canShareFiles) {
      var share = document.createElement("button");
      share.type = "button";
      share.className = "share";
      share.textContent = t("📤 Share");
      share.addEventListener("click", function () {
        shareUrl(src, (job.media === "video" ? "my-video-" : "my-picture-") + job.id +
          (job.media === "video" ? ".mp4" : ".png"), share);
      });
      actions.appendChild(share);
    }

    // Last, and the only red thing in the row.
    if (job.filename) {
      actions.appendChild(binButton(card, [job.filename], function () {
        resultGone(card);
        offerUndo([job.filename], function () { renderResult(card, job); });
      }));
    }

    return actions;
  }

  // A film is several clips *and* the one film they were joined into. The film
  // is what they asked for, so that is what plays; the parts are in their gallery
  // if they want them.
  function renderFilm(card, job) {
    var movie = job.extra && job.extra.movie;
    if (!movie) { card.result.hidden = true; return; }
    card.result.innerHTML = "";
    var src = "/api/gallery/" + encodeURIComponent(movie) + "/file?v=" + job.id;

    var media = document.createElement("video");
    media.src = src;
    media.controls = true;
    media.playsInline = true;
    media.preload = "metadata";
    media.poster = "/api/gallery/" + encodeURIComponent(movie) + "/poster?v=" + job.id;
    card.result.appendChild(media);

    var beats = (job.extra && job.extra.beats) || [];
    if (beats.length) {
      var list = document.createElement("ol");
      list.className = "film-parts";
      beats.forEach(function (beat) {
        var li = document.createElement("li");
        li.textContent = beat.says ? "\u201c" + beat.says + "\u201d" : beat.scene;
        list.appendChild(li);
      });
      card.result.appendChild(list);
    }

    var actions = document.createElement("div");
    actions.className = "actions";
    var download = document.createElement("a");
    download.href = "/api/gallery/" + encodeURIComponent(movie) + "/file?v=" + job.id + "&download=1";
    download.setAttribute("download", movie);
    download.textContent = t("⬇︎ Save my film");
    actions.appendChild(download);

    var again = document.createElement("button");
    again.type = "button";
    again.className = "again";
    again.textContent = t("🎲 Try again");
    again.addEventListener("click", function () { tryAgain(card); });
    actions.appendChild(again);

    // The film, and only the film. Each clip it was joined from is a video of
    // theirs on its own shelf, and binning four things when they asked to bin one
    // is not what a bin button promises.
    actions.appendChild(binButton(card, [movie], function () {
      resultGone(card);
      offerUndo([movie], function () { renderFilm(card, job); });
    }));

    card.result.appendChild(actions);
    card.result.hidden = false;
    refreshMine();
  }

  // Four at once is four runs of one graph, one after another, so the grid
  // fills in as they land: a tile appears a second or two after its picture
  // exists, with its own buttons, while the rest are still being drawn. The
  // state lives on the card, so the next poll adds a tile rather than
  // rebuilding the grid - a rebuild would forget which ones they had binned.

  function choiceState(card, job) {
    if (card.choices && card.choices.id === job.id) return card.choices;
    var state = { id: job.id, names: [], tiles: {}, binned: {}, kept: null,
                  grid: document.createElement("div"), actions: null };
    state.grid.className = "grid";
    card.result.innerHTML = "";
    card.result.appendChild(state.grid);
    card.result.hidden = false;
    card.choices = state;
    return state;
  }

  // Binned and back again, in one place: "Keep this one" bins the others, each
  // tile's own bin takes just that one, and undo puts any of them back.
  function markBinned(state, figure, on) {
    figure.classList.toggle("binned", on);
    var keep = figure.querySelector(".pick");
    var drop = figure.querySelector(".bin-one");
    if (keep) {
      keep.textContent = on ? t("In the trash") : t("Keep this one");
      keep.disabled = on;
    }
    if (drop) drop.hidden = on || !!state.kept;
  }

  function addChoice(card, job, state, name) {
    var figure = document.createElement("figure");
    var img = document.createElement("img");
    img.src = "/api/gallery/" + encodeURIComponent(name) + "/thumb?v=" + job.id;
    img.alt = t("One of the pictures you made");
    img.addEventListener("click", function () { openViewerById(name); });
    var pick = document.createElement("button");
    pick.type = "button";
    pick.className = "pick";
    pick.textContent = t("Keep this one");
    pick.addEventListener("click", function () {
      if (state.kept === name) return;
      state.kept = name;
      // They have seen the one they want and the rest have not been drawn yet,
      // so there is nothing to wait for: stopping keeps everything already
      // made and spends no more of the day on pictures they are about to bin.
      if (card.jobId === job.id) stop(card);
      Array.prototype.forEach.call(state.grid.children, function (f) {
        f.classList.toggle("chosen", f === figure);
      });
      pick.textContent = t("✓ Kept");
      // The others go to the trash, so a change of heart is one tap away on
      // the parent page rather than gone. Any they have already binned themselves
      // are not sent again - the route refuses an empty list.
      binRivals(state, name);
      Array.prototype.forEach.call(state.grid.children, function (f) {
        if (f !== figure) markBinned(state, f, true);
      });
      // The kept one's own bin would now be a second name for the Delete in
      // the row below it.
      drop.hidden = true;
      keptActions(card, job, state);
    });
    // One of four they can see is wrong straight away - a fox with three
    // ears - should not have to be kept until they have chosen a favourite.
    // The glyph alone, because two worded buttons do not fit a tile on a
    // phone; arming turns it into a question that does.
    var drop = document.createElement("button");
    drop.type = "button";
    drop.className = "bin-one";
    drop.textContent = "🗑️";
    drop.title = t("Delete this one");
    drop.setAttribute("aria-label", t("Delete this one"));
    drop.addEventListener("click", function () {
      if (!arm(drop, "Really?")) return;
      disarm();
      drop.disabled = true;
      binThem([name])
        .then(function () {
          state.binned[name] = true;
          markBinned(state, figure, true);
          offerUndo([name], function () {
            state.binned[name] = false;
            drop.disabled = false;
            markBinned(state, figure, false);
          });
        })
        .catch(function (err) {
          drop.disabled = false;
          showToast(err.message || GENERIC_ERROR, { ms: 8000 });
        });
    });

    figure.appendChild(img);
    figure.appendChild(pick);
    figure.appendChild(drop);
    state.grid.appendChild(figure);
    state.names.push(name);
    state.tiles[name] = figure;
    // One that landed after they had already chosen. It is a finished picture
    // of theirs either way, so it goes where the others they did not pick went,
    // with the same undo, rather than quietly disappearing.
    if (state.kept && state.kept !== name) {
      binRivals(state, state.kept);
      markBinned(state, figure, true);
    }
    return figure;
  }

  function binRivals(state, keep) {
    var rest = state.names.filter(function (n) {
      return n !== keep && !state.binned[n];
    });
    if (!rest.length) return;
    rest.forEach(function (n) { state.binned[n] = true; });
    binThem(rest).then(function () { refreshAllowance(); }).catch(function () {});
  }

  // From here on it is one picture, and it gets one picture's buttons: save
  // *it*, animate it, cut it out, keep whoever is in it.
  function keptActions(card, job, state) {
    var kept1 = { id: job.id, kind: job.kind, media: "image",
                  filename: state.kept, filenames: [state.kept] };
    var row = singleActions(card, kept1, resultUrl(kept1));
    if (state.actions) state.actions.replaceWith(row);
    else card.result.appendChild(row);
    state.actions = row;
  }

  // Everything that has landed so far, in the grid. Called on every poll while
  // the job runs and once more when it is over.
  function growChoices(card, job) {
    var state = choiceState(card, job);
    (job.filenames || []).forEach(function (name) {
      if (!state.tiles[name]) addChoice(card, job, state, name);
    });
    return state;
  }

  function renderChoices(card, job) {
    var state = growChoices(card, job);
    if (state.kept) { keptActions(card, job, state); return; }

    var actions = document.createElement("div");
    actions.className = "actions";
    var again = document.createElement("button");
    again.type = "button";
    again.className = "again";
    again.textContent = t("🎲 Try again");
    again.addEventListener("click", function () { tryAgain(card); });
    actions.appendChild(again);
    var all = document.createElement("a");
    all.href = "/api/gallery/zip?ids=" + state.names.map(encodeURIComponent).join(",");
    all.setAttribute("download", "");
    all.textContent = t("⬇︎ Save them all");
    actions.appendChild(all);
    if (state.actions) state.actions.replaceWith(actions);
    else card.result.appendChild(actions);
    state.actions = actions;
    card.result.hidden = false;
  }

  // --- laying out a comic page ---------------------------------------------
  // Drawn in the browser, like the card maker and the film title card: the
  // server has no font files and needs none, and the layout can be changed
  // without a rebuild. The finished page goes back through /api/upload, so it
  // lands in the gallery like anything else and can be printed or shared.

  var COMIC_W = 1200;

  function comicLayout(count) {
    if (count <= 3) return { cols: 1, rows: 3 };
    if (count <= 4) return { cols: 2, rows: 2 };
    return { cols: 2, rows: 3 };
  }

  function wrapText(ctx, text, maxWidth) {
    var words = String(text).split(/\s+/), lines = [], line = "";
    words.forEach(function (word) {
      var test = line ? line + " " + word : word;
      if (ctx.measureText(test).width > maxWidth && line) {
        lines.push(line);
        line = word;
      } else {
        line = test;
      }
    });
    if (line) lines.push(line);
    return lines;
  }

  function drawComic(job) {
    var names = job.filenames || [];
    var panels = (job.extra && job.extra.panels) || [];
    var grid = comicLayout(names.length);
    var pad = 24, gap = 18, titleH = 92;
    var cellW = Math.floor((COMIC_W - pad * 2 - gap * (grid.cols - 1)) / grid.cols);
    // Panels are square pictures; the strip under each holds what they say.
    var sayH = 74;
    var cellH = cellW + sayH;
    var rows = Math.ceil(names.length / grid.cols);
    var height = titleH + pad + rows * cellH + (rows - 1) * gap + pad;

    var canvas = document.createElement("canvas");
    canvas.width = COMIC_W;
    canvas.height = height;
    var c = canvas.getContext("2d");
    c.fillStyle = "#fffdf6";
    c.fillRect(0, 0, COMIC_W, height);

    var title = (job.extra && job.extra.title) || t("My comic");
    c.fillStyle = "#21104a";
    c.textAlign = "center";
    c.font = "800 44px ui-rounded, -apple-system, system-ui, sans-serif";
    c.fillText(title.slice(0, 46), COMIC_W / 2, 62);

    var loaded = names.map(function (name) {
      var img = new Image();
      img.src = "/api/gallery/" + encodeURIComponent(name) + "/file?v=" + job.id;
      return img;
    });

    return Promise.all(loaded.map(function (img) {
      return img.decode ? img.decode().catch(function () {}) : Promise.resolve();
    })).then(function () {
      loaded.forEach(function (img, i) {
        var col = i % grid.cols, row = Math.floor(i / grid.cols);
        var x = pad + col * (cellW + gap);
        var y = titleH + pad + row * (cellH + gap);

        c.save();
        c.beginPath();
        c.roundRect(x, y, cellW, cellW, 14);
        c.clip();
        c.fillStyle = "#000";
        c.fillRect(x, y, cellW, cellW);
        if (img.naturalWidth) {
          // The pictures are square and so is the cell, but cover-fit anyway
          // rather than trusting that forever.
          var scale = Math.max(cellW / img.naturalWidth, cellW / img.naturalHeight);
          var w = img.naturalWidth * scale, h = img.naturalHeight * scale;
          c.drawImage(img, x + (cellW - w) / 2, y + (cellW - h) / 2, w, h);
        }
        c.restore();

        c.strokeStyle = "#21104a";
        c.lineWidth = 5;
        c.beginPath();
        c.roundRect(x + 2.5, y + 2.5, cellW - 5, cellW - 5, 14);
        c.stroke();

        // The number, so the order is never in doubt.
        c.fillStyle = "#21104a";
        c.beginPath();
        c.roundRect(x + 12, y + 12, 44, 38, 10);
        c.fill();
        c.fillStyle = "#fff";
        c.textAlign = "center";
        c.font = "800 24px ui-rounded, -apple-system, system-ui, sans-serif";
        c.fillText(String(i + 1), x + 34, y + 39);

        var says = (panels[i] && panels[i].says) || "";
        if (says) {
          c.textAlign = "left";
          c.font = "600 25px ui-rounded, -apple-system, system-ui, sans-serif";
          var lines = wrapText(c, '\u201c' + says + '\u201d', cellW - 34).slice(0, 2);
          var boxH = 14 + lines.length * 30;
          c.fillStyle = "#fff";
          c.strokeStyle = "#21104a";
          c.lineWidth = 3;
          c.beginPath();
          c.roundRect(x + 6, y + cellW + 10, cellW - 12, boxH, 12);
          c.fill();
          c.stroke();
          c.fillStyle = "#21104a";
          lines.forEach(function (line, n) {
            c.fillText(line, x + 22, y + cellW + 36 + n * 30);
          });
        }
      });
      return canvas;
    });
  }

  function renderComic(card, job) {
    card.result.innerHTML = "";
    var note = document.createElement("p");
    note.className = "msg";
    note.textContent = t("Putting your comic together...");
    card.result.appendChild(note);
    card.result.hidden = false;

    drawComic(job).then(function (canvas) {
      canvas.toBlob(function (blob) {
        var form = new FormData();
        form.append("photo", blob, "comic.png");
        form.append("source", "comic");
        form.append("message", (job.extra && job.extra.title) || "");
        fetch("/api/upload", { method: "POST", body: form })
          .then(readJSON)
          .then(function (data) {
            showComicPage(card, data.gallery_id);
            refreshMine();
          })
          .catch(function (err) {
            note.textContent = err.message || GENERIC_ERROR;
            note.classList.add("bad");
          });
      }, "image/png");
    });
  }

  // The finished sheet and its buttons. Its own function so undo can put it
  // straight back: drawing the page again would mean laying it out and
  // uploading it a second time, which is a whole new comic in the gallery.
  function showComicPage(card, id) {
    card.result.innerHTML = "";
    var img = document.createElement("img");
    img.src = "/api/gallery/" + encodeURIComponent(id) + "/file";
    img.alt = t("Your comic");
    img.addEventListener("click", function () { openViewerById(id); });
    card.result.appendChild(img);

    var actions = document.createElement("div");
    actions.className = "actions";
    var save = document.createElement("a");
    save.href = "/api/gallery/" + encodeURIComponent(id) + "/file?download=1";
    save.setAttribute("download", "");
    save.textContent = t("⬇︎ Save my comic");
    actions.appendChild(save);
    var again = document.createElement("button");
    again.type = "button";
    again.className = "again";
    again.textContent = t("🎲 Try again");
    again.addEventListener("click", function () { tryAgain(card); });
    actions.appendChild(again);
    if (canShareFiles) {
      var share = document.createElement("button");
      share.type = "button";
      share.className = "share";
      share.textContent = t("📤 Share");
      share.addEventListener("click", function () {
        shareUrl("/api/gallery/" + encodeURIComponent(id) + "/file",
          "my-comic.png", share);
      });
      actions.appendChild(share);
    }
    // The page, not the panels. Each panel is a picture of theirs on the Comic
    // panels shelf, and several of them are usually worth keeping even when
    // the sheet they were laid out on is not - so binning the page quietly
    // binning six other things would be a delete they did not ask for. "Keep
    // this one" bins the leftovers because those are rivals to the same
    // picture; panels are parts of this one, which is a different thing.
    actions.appendChild(binButton(card, [id], function () {
      resultGone(card);
      offerUndo([id], function () { showComicPage(card, id); });
    }));
    card.result.appendChild(actions);
    card.result.hidden = false;
  }

  // --- polling ------------------------------------------------------------

  function poll(card, jobId) {
    clearTimeout(card.timer);
    card.timer = setTimeout(function () {
      fetch("/api/job/" + jobId)
        .then(function (r) {
          if (!r.ok) throw new Error(GENERIC_ERROR);
          return r.json();
        })
        .then(function (job) {
          if (card.jobId !== jobId) return; // superseded or stopped

          if (job.status === "cancelled") {
            setTitle("");
            if (card.sys) card.sys.hidden = true;
            card.status.hidden = false;
            card.bar.classList.remove("waiting");
            card.fill.style.width = "0%";
            card.pct.textContent = "";
            card.timing.hidden = true;
            showStatus(card, job.message, false);
            card.jobId = null;
            setIdle();
            hideNow();
            return;
          }
          if (job.status === "error") {
            fail(card, job.error);
            return;
          }
          if (job.status === "done") {
            setProgress(card, 1);
            showStatus(card, job.message, false);
            card.timing.textContent = t("Took {time}.", { time: clock(job.elapsed) });
            card.timing.hidden = job.elapsed < 3;
            if (card.sys) card.sys.hidden = true;
            if (card.kind === "story") storyLanded(card, job);
            else renderResult(card, job);
            card.jobId = null;
            setIdle();
            flashTitle(t("✅ Ready!"));
            finishNow(job);
            ding();
            refreshMine();
            refreshAllowance();
            cheerMilestone(job.milestone);
            return;
          }
          setProgress(card, job.progress);
          showStatus(card, job.message, false);
          // Four at once, half way: the ones already drawn go straight onto
          // the page instead of waiting for the last one.
          if (job.kind === "image" && job.wanted > 1 &&
              job.filenames && job.filenames.length) {
            growChoices(card, job);
          }
          showPlan(card, job);
          showTiming(card, job);
          showSystem(card, job);
          showNow(card, job);
          poll(card, jobId);
        })
        .catch(function () {
          // A blip on the wifi should not kill a five-minute render.
          if (card.jobId === jobId) poll(card, jobId);
        });
    }, POLL_MS);
  }

  // --- submit and stop ----------------------------------------------------

  function submit(card) {
    if (card.kind === "story") { storyGo(card); return; }
    var prompt = card.textarea.value.trim();
    if (!prompt) {
      fail(card, t("Type something you'd like to make first!"));
      return;
    }

    var kind = card.kind === "video" ? currentMode() : card.kind;
    if (kind === "music") {
      var lyrics = card.lyrics ? card.lyrics.value.trim() : "";
      var songBody = {
        prompt: prompt,
        lyrics: lyrics,
        // Singing with no words written is music with nobody singing - the
        // server reads it the same way. Saying so here keeps the two ends
        // agreeing about what was asked for.
        singing: card.singing && !!lyrics,
        seconds: card.seconds,
        // Which of the three chips. The server clamps the length to this
        // kind's own bounds and forces [inst] for the two that do not sing,
        // so a page that has drifted cannot ask for a two-minute jingle.
        kind: card.soundKind || "song",
      };
      var songStyles = chosenStyles(card);
      if (Object.keys(songStyles).length) songBody.styles = songStyles;
      card.lastBody = { kind: "music", body: songBody };
      startJob(card, card.lastBody, t("Writing your song..."));
      return;
    }
    if (kind === "story") {
      var filmBody = {
        prompt: prompt, parts: card.parts, orientation: card.orientation,
        duration: card.seconds, quality: card.quality || "normal",
      };
      if (card.character) filmBody.character = card.character;
      var filmStyles = chosenStyles(card);
      if (Object.keys(filmStyles).length) filmBody.styles = filmStyles;
      card.lastBody = { kind: "story", body: filmBody };
      startJob(card, card.lastBody, t("Working out your story..."));
      return;
    }
    if (kind === "comic") {
      var comicBody = { prompt: prompt, panels: card.panels, character: card.character };
      var comicStyles = chosenStyles(card);
      if (Object.keys(comicStyles).length) comicBody.styles = comicStyles;
      card.lastBody = { kind: "comic", body: comicBody };
      startJob(card, card.lastBody, t("Reading your story..."));
      return;
    }
    var body = { prompt: prompt, orientation: card.orientation };
    if (card.character) body.character = card.character;
    if (card.kind === "image" && card.count > 1) body.count = card.count;
    if (card.cutout) body.cutout = true;
    var picked = chosenStyles(card);
    if (Object.keys(picked).length) body.styles = picked;

    if (card.kind === "video") {
      body.duration = card.seconds;
      if (card.quality && card.quality !== "normal") body.quality = card.quality;
      if (card.say && card.say.value.trim()) body.dialogue = card.say.value.trim();
      if (card.effectPick && card.effectPick.value) {
        body.effect = card.effectPick.value;
        body.effect_at = (card.effectWhen && card.effectWhen.value) || "start";
      }
      if (kind === "i2v") {
        if (!source) {
          fail(card, t("Pick a picture first — make one above, or use a photo!"));
          return;
        }
        if (source.jobId) body.source_job_id = source.jobId;
        if (source.galleryId) body.source_gallery_id = source.galleryId;
      }
      if (kind === "flf") {
        if (!slots.first || !slots.last) {
          fail(card, t("Pick a picture to start on and one to end on!"));
          return;
        }
        body.first_gallery_id = slots.first.id;
        body.last_gallery_id = slots.last.id;
      }
    }

    card.lastBody = { kind: kind, body: body };
    startJob(card, withSeed(card, card.lastBody), t("Sending it off..."));
  }

  // "Make it again, but..." hands the old seed to the *next* generation and no
  // further. lastBody keeps no seed on purpose: the "Try again" button under
  // the result means "give me a different one", and a remembered seed would
  // quietly turn it into "give me that again".
  function withSeed(card, what) {
    if (card.tweakSeed === null || card.tweakSeed === undefined) return what;
    var seeded = { kind: what.kind, body: Object.assign({}, what.body, { seed: card.tweakSeed }) };
    card.tweakSeed = null;
    return seeded;
  }

  function startJob(card, what, firstWords) {
    armDing();
    setBusy(card);
    clearResult(card);
    if (card.plan) card.plan.hidden = true;
    // The picture card has no idea helper, so this element may not exist.
    if (card.helperMsg) card.helperMsg.hidden = true;
    card.status.hidden = false;
    card.timing.hidden = true;
    setProgress(card, 0);
    showStatus(card, firstWords, false);
    // Their own words go in too, so the sheet is not blank for the second
    // between tapping Go and the first poll coming back.
    showNow(card, { kind: what.kind, progress: 0, message: firstWords,
                    idea: (what.body && what.body.prompt) || "" });
    // The bar sits under the button; on a phone that can be below the fold,
    // and a tap that seems to do nothing reads as broken.
    card.status.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTitle(t("Starting"));

    postJSON("/api/generate/" + what.kind, what.body)
      .then(function (data) {
        card.jobId = data.job_id;
        showStatus(card, t("Getting started..."), false);
        loadHistory();
        poll(card, data.job_id);
      })
      .catch(function (err) {
        fail(card, err.message);
        // If that was "no more today", the countdown should agree with it.
        refreshAllowance();
      });
  }

  function tryAgain(card) {
    if (!card.lastBody || activeCard) return;
    var again = card.lastBody;
    armDing();
    setBusy(card);
    clearResult(card);
    card.status.hidden = false;
    card.timing.hidden = true;
    setProgress(card, 0);
    showStatus(card, t("Making another one..."), false);
    card.status.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTitle(t("Starting"));
    postJSON("/api/generate/" + again.kind, again.body)
      .then(function (data) {
        card.jobId = data.job_id;
        poll(card, data.job_id);
      })
      .catch(function (err) { fail(card, err.message); refreshAllowance(); });
  }

  function stop(card) {
    if (!card.jobId) return;
    var jobId = card.jobId;
    card.stop.disabled = true;
    showStatus(card, t("Stopping..."), false);

    fetch("/api/job/" + jobId + "/cancel", { method: "POST" })
      .then(function (r) { return r.json().catch(function () { return null; }); })
      .then(function (job) {
        // Stopped four at once with two already drawn: those two are finished
        // pictures in their gallery, and the server ends the job with them
        // rather than throwing them away. So this leaves the poll running and
        // lets the usual "it's ready" path draw what they have - saying nothing
        // was made over two pictures they are looking at would be a lie.
        if (job && job.filenames && job.filenames.length) {
          showStatus(card, t("Stopping..."), false);
          poll(card, jobId);
          return;
        }
        clearTimeout(card.timer);
        card.jobId = null;
        setTitle("");
        card.bar.classList.remove("waiting");
        card.fill.style.width = "0%";
        card.pct.textContent = "";
        card.timing.hidden = true;
        showStatus(card, t("Stopped! Nothing was made. Try a different idea."), false);
      })
      .catch(function () {
        showStatus(card, t("Couldn't stop it — it may finish anyway."), true);
      })
      .then(function () {
        card.stop.disabled = false;
        setIdle();
      });
  }

  // --- gallery -------------------------------------------------------------
  // Reads ComfyUI's output directory through the backend. Everything they have
  // ever made is in there, including things made before this page existed,
  // which simply show without a prompt.

  var mineCard = document.getElementById("card-mine");
  var mineNote = mineCard.querySelector(".mine-note");
  var mineEmpty = mineCard.querySelector(".mine-empty");
  var mineSettings = mineCard.querySelector(".settings");
  var mineTools = mineCard.querySelector(".mine-tools");
  var mineOrder = mineCard.querySelector(".mine-order");
  // Only the shelves that hold gallery items. The characters shelf above them
  // is a row of faces painted from the cast, not from the listing.
  var mineShelves = mineCard.querySelectorAll(".shelf[data-media]");
  var mineGrid = mineCard.querySelector(".mine-grid");
  var mineNone = mineCard.querySelector(".mine-none");
  var castShelf = mineCard.querySelector(".cast-shelf");
  var castStrip = mineCard.querySelector(".cast-strip");
  // All this sheet does now is pick a picture for something else.
  var sheet = document.getElementById("gallery");
  var shelves = sheet.querySelectorAll(".shelf");
  var sheetEmpty = sheet.querySelector(".sheet-empty");
  var viewer = document.getElementById("viewer");
  var viewerMedia = viewer.querySelector(".viewer-media");
  var viewerPrompt = viewer.querySelector(".viewer-prompt");
  var viewerLyrics = viewer.querySelector(".viewer-lyrics");
  var viewerFacts = viewer.querySelector(".viewer-facts");
  var viewerSave = viewer.querySelector(".viewer-save");
  var viewerDelete = viewer.querySelector(".viewer-delete");
  var viewerAnimate = viewer.querySelector(".viewer-animate");
  var viewerCast = viewer.querySelector(".viewer-cast");
  var viewerVoice = viewer.querySelector(".viewer-voice");
  var viewerName = viewer.querySelector(".viewer-name");
  var viewerTags = viewer.querySelector(".viewer-tags");
  var viewerNext = viewer.querySelector(".viewer-next");
  var viewerTweak = viewer.querySelector(".viewer-tweak");
  var viewerSticker = viewer.querySelector(".viewer-sticker");
  var viewerSound = viewer.querySelector(".viewer-sound");
  var viewerFrame = viewer.querySelector(".viewer-frame");
  var viewerSmooth = viewer.querySelector(".viewer-smooth");
  var viewerSlow = viewer.querySelector(".viewer-slow");
  var viewerLoop = viewer.querySelector(".viewer-loop");
  var viewerHuge = viewer.querySelector(".viewer-huge");
  var viewerRestyle = viewer.querySelector(".viewer-restyle");
  var viewerChange = viewer.querySelector(".viewer-change");
  var viewerOutside = viewer.querySelector(".viewer-outside");
  var viewerFix = viewer.querySelector(".viewer-fix");
  var viewerShare = viewer.querySelector(".viewer-share");
  var viewerFav = viewer.querySelector(".viewer-fav");
  var viewerFamily = viewer.querySelector(".viewer-family");
  var viewerMaker = viewer.querySelector(".viewer-maker");
  var viewerAsked = viewer.querySelector(".viewer-asked");
  var viewerLive = viewer.querySelector(".viewer-actions.live");
  var viewerTrashed = viewer.querySelector(".viewer-actions.trashed");
  var trashBox = mineCard.querySelector(".trash");
  var trashGrid = mineCard.querySelector(".trash-grid");
  var trashNote = mineCard.querySelector(".trash-note");
  var trashCount = trashBox.querySelector(".count");
  var viewing = null;
  var viewingTrashed = false;
  var viewerFromPicker = false;

  var selectBtn = mineCard.querySelector(".sheet-select");
  var pickedBar = mineCard.querySelector(".picked-bar");
  var pickedCount = mineCard.querySelector(".picked-count");
  var pickedSave = mineCard.querySelector(".picked-save");
  var pickedAll = mineCard.querySelector(".picked-all");
  var pickedDelete = mineCard.querySelector(".picked-delete");
  var pickedJoin = mineCard.querySelector(".picked-join");
  var pickedCompare = mineCard.querySelector(".picked-compare");
  var joinSheet = document.getElementById("join");
  var joinTitle = joinSheet.querySelector(".join-title");
  var joinNote = joinSheet.querySelector(".join-note");
  var joinStatus = joinSheet.querySelector(".join-status");
  var joinGo = joinSheet.querySelector(".join-go");
  var titlePreview = joinSheet.querySelector(".title-preview");
  var shownItems = [];   // the listing behind `shown`, for looking ids up
  var choosing = false;
  var chosen = [];      // ids, in the order they tapped them
  var shown = [];       // everything currently on screen, for "Choose all"

  // Always address a gallery file with its version, never bare: filenames get
  // reused after a delete, so a bare URL can hand back a cached older file.
  function fileUrl(item, extra) {
    return "/api/gallery/" + encodeURIComponent(item.id) + "/file?v=" +
      encodeURIComponent(item.version || 0) + (extra || "");
  }

  // Which shelf a thing belongs on. Everything that is not a plain picture is
  // matched by its kind first, so the Pictures shelf is only ever pictures they
  // asked for directly - not comic panels, not photos, not a finished comic.
  var BY_KIND = {
    upload: "upload", comic: "comic", panel: "panel", sticker: "sticker",
    // A grabbed frame is a picture like any other, and a video with a sound or
    // their voice on it is still a video.
    frame: "image", voice: "video", sound: "video", movie: "video", flf: "video",
    // A story film is a film with a song on it. It belongs beside the films,
    // with a badge of its own so they can tell it from the film it was made of.
    storyfilm: "video",
    // A tune and a hum are sounds they made, and they belong beside them
    // songs: one shelf for everything that plays without a picture. The
    // badge on each tile is what says which it is.
    music: "music", jingle: "music", ambience: "music",
    // A smoothed or slowed clip is still a video, a moving sticker is still a
    // sticker, and a picture made huge is still a picture.
    smooth: "video", slowmo: "video", loop: "sticker", huge: "image",
    // All three Klein edits are pictures, and belong on the Pictures shelf
    // next to the one they started from. So is a restyled one: a clay model of
    // their drawing is a picture of a clay model.
    edit: "image", outpaint: "image", inpaint: "image", restyle: "image",
  };

  // Which shelf a thing lives on, as one answer both views use: the shelves
  // themselves, and "by kind" in the one long list, which is these groups
  // flattened into the order the shelves are in.
  function homeOf(item) {
    return BY_KIND[item.kind] ||
      (item.media === "video" ? "video" : item.media === "audio" ? "music" : "image");
  }

  var SHELF_ORDER = ["image", "video", "music", "comic", "panel", "sticker", "upload"];

  function shelfMatch(shelf, item) {
    var want = shelf.dataset.media;
    // Somebody else's, shared to the family shelf. It lives on that shelf and
    // nowhere else: Pictures is theirs, and a star on a sibling's picture is
    // theirs, so neither shelf should be counting other people's things.
    if (item.mine === false) return want === "family" && severalWho;
    // Their own shared things sit on it too - they have to be able to see what they
    // has put out there before they can decide to take it back.
    if (want === "family") return severalWho && !!item.family;
    if (want === "favourite") return !!item.favourite;
    return want === homeOf(item);
  }

  function isUpload(item) { return item.kind === "upload" || item.kind === "comic"; }

  // Things that came from a prompt, so "make another like this" means
  // something. A sticker, a grabbed frame, a joined film and a video with a
  // sound on it were all made *from* something else.
  var NOT_REMAKEABLE = ["movie", "storyfilm", "sticker", "frame", "sound", "voice",
                        "smooth", "slowmo", "loop", "huge",
                        // An edit is a change to a picture, not a description
                        // of one: putting "make it night-time" into the
                        // picture card would ask for a picture of that. A
                        // restyle is the same - "turn it into a clay model"
                        // typed into the picture card asks for clay.
                        "edit", "outpaint", "inpaint", "restyle"];
  // The three that start from a picture they already have. "Make it again,
  // but..." on one of these means the *sheet* again, on the same picture.
  var EDIT_KINDS = ["edit", "outpaint", "inpaint"];
  function isEdit(item) { return EDIT_KINDS.indexOf(item && item.kind) !== -1; }
  function canRemake(item) {
    return !isUpload(item) && NOT_REMAKEABLE.indexOf(item.kind) === -1;
  }

  // The trash is on the page now rather than in a sheet they had to open, and
  // it is folded shut. Its tiles are only built when they unfold it: a trashed
  // video tile is a <video> asking the network for a frame, and fifteen of
  // those behind a closed summary is work nobody asked for.
  var trashItems = [];

  function loadTrash() {
    fetch("/api/gallery/trash")
      .then(readJSON)
      .then(function (data) {
        trashItems = data.items || [];
        trashBox.hidden = trashItems.length === 0;
        trashCount.textContent = trashItems.length ? "(" + trashItems.length + ")" : "";
        trashNote.textContent =
          t("Things stay here for {days} days, then they're gone for good. Tap one to put it back.",
            { days: Math.round(data.days || 7) });
        trashGrid.innerHTML = "";
        if (trashBox.open) paintTrash();
      })
      .catch(function () { trashBox.hidden = true; });
  }

  function paintTrash() {
    trashGrid.innerHTML = "";
    trashItems.forEach(function (item) { trashGrid.appendChild(makeTrashTile(item)); });
  }

  trashBox.addEventListener("toggle", function () {
    if (trashBox.open && !trashGrid.children.length) paintTrash();
  });

  function posterUrl(item) {
    return "/api/gallery/" + encodeURIComponent(item.id) + "/poster?v=" +
      encodeURIComponent(item.version || 0);
  }

  // One flat SVG, inline so it needs no request and no file in static/.
  var SONG_TILE = "data:image/svg+xml;utf8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 40">' +
    '<rect width="64" height="40" fill="#1a1033"/>' +
    '<g fill="#78d1ff"><rect x="10" y="14" width="3" height="12" rx="1.5"/>' +
    '<rect x="17" y="9" width="3" height="22" rx="1.5"/>' +
    '<rect x="24" y="17" width="3" height="6" rx="1.5"/>' +
    '<rect x="31" y="6" width="3" height="28" rx="1.5"/>' +
    '<rect x="38" y="13" width="3" height="14" rx="1.5"/>' +
    '<rect x="45" y="18" width="3" height="4" rx="1.5"/>' +
    '<rect x="52" y="11" width="3" height="18" rx="1.5"/></g></svg>');

  var BADGE = {
    comic: "📖 Comic",
    panel: "🧩 Panel",
    upload: "📷 Photo",
    movie: "🎬 Film",
    storyfilm: "🎭 Story film",
    voice: "🎤 My voice",
    sound: "🔊 Sound",
    sticker: "✂️ Sticker",
    frame: "📸 From a video",
    flf: "🎞️ Two pictures",
    music: "🎵 Song",
    jingle: "🎺 Little tune",
    ambience: "🌊 Background hum",
    smooth: "✨ Smooth",
    slowmo: "🐌 Slow motion",
    loop: "🌀 Moving sticker",
    huge: "🔍 Huge",
    edit: "🪄 Changed",
    outpaint: "🔭 More of it",
    inpaint: "🩹 Fixed a bit",
    restyle: "🎨 A new style",
  };

  // What kind of thing this is, in their words, on every tile - which is what
  // makes one grid of all of it readable. The shelf headings say it in the
  // grouped view; the badge says it in either.
  function kindLabel(item) {
    return t(BADGE[item.kind]
      || (item.source === "drawing" ? "✏️ Drawing" : item.source === "card" ? "💌 Card" : null)
      || (item.media === "video" ? "▶ Video"
          : item.media === "audio" ? "🎵 Song" : "Picture"));
  }

  // Whose a thing is, as a profile. An empty `who` is a file made before
  // profiles existed and belongs to whoever carries `adopts` - the server says
  // the same thing with `mine`, and this is only ever asked about items it has
  // already said are not theirs.
  function makerOf(item) {
    for (var i = 0; i < whoAll.length; i++) {
      if (item.who ? whoAll[i].id === item.who : whoAll[i].adopts) return whoAll[i];
    }
    return null;
  }

  function makerChip(item) {
    var who = makerOf(item);
    if (!who) return null;
    var chip = document.createElement("span");
    chip.className = "maker";
    var pic = document.createElement("span");
    pic.className = "maker-face";
    faceInto(pic, who);
    var name = document.createElement("span");
    name.className = "maker-name";
    name.textContent = who.name;
    chip.appendChild(pic);
    chip.appendChild(name);
    return chip;
  }

  function makeTile(item) {
    var tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";

    // Every tile is a plain image, videos included: the server cuts a still
    // from the first frame. iOS only lets a handful of <video> elements decode
    // at once and past that they render blank, which is what a grid of twenty
    // live videos looked like on a phone.
    var media = document.createElement("img");
    media.alt = item.idea || item.prompt || t("Something you made");
    media.loading = "lazy";
    media.decoding = "async";
    if (item.media === "audio") {
      // The drawn waveform, not the mp3: an <img src="...mp3"> is a broken
      // image icon, which is what a song tile was showing.
      media.src = posterUrl(item);
    } else if (item.media === "video") {
      media.src = posterUrl(item);
      media.addEventListener("error", function () {
        // No poster (undecodable file, or an old ffmpeg-less container):
        // fall back to the video element and ask Safari for a frame.
        var v = document.createElement("video");
        v.muted = true;
        v.playsInline = true;
        v.preload = "metadata";
        v.src = fileUrl(item) + "#t=0.1";
        tile.replaceChild(v, media);
      }, { once: true });
    } else {
      media.src = fileUrl(item);
    }
    tile.appendChild(media);

    var badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = kindLabel(item);
    tile.appendChild(badge);

    if (item.name) {
      var caption = document.createElement("span");
      caption.className = "tile-name";
      caption.textContent = item.name;
      tile.appendChild(caption);
    }

    if (item.favourite) {
      var star = document.createElement("span");
      star.className = "star";
      star.textContent = "⭐";
      tile.appendChild(star);
    }

    // Whose it is, on the tile itself. The one thing this shelf must never do
    // is let somebody else's picture read as theirs.
    if (item.mine === false) {
      var maker = makerChip(item);
      if (maker) tile.appendChild(maker);
    } else {
      var tick = document.createElement("span");
      tick.className = "tick";
      tick.textContent = "✓";
      tile.appendChild(tick);
    }

    tile.dataset.itemId = item.id;
    tile.addEventListener("click", function () {
      // Not theirs: there to look at, not to pick. Choosing feeds delete, tag,
      // join and the "pick a picture" handoffs, and the server refuses every
      // one of those on somebody else's file - so the tile should not offer it.
      if (item.mine === false) { openViewer(item); return; }
      if (picking) { var take = picking; picking = null; closeGallery(); take(item); return; }
      if (choosing) togglePick(item.id);
      else openViewer(item);
    });
    return tile;
  }

  function makeTrashTile(item) {
    var tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    var url = "/api/gallery/trash/" + encodeURIComponent(item.id) + "/file?v=" + item.version;
    var media;
    if (item.media === "video") {
      media = document.createElement("video");
      media.muted = true; media.playsInline = true; media.preload = "metadata";
      media.src = url + "#t=0.1";
    } else {
      media = document.createElement("img");
      media.loading = "lazy";
      // A song is its waveform, drawn and cached under a "trash-" prefix so a
      // deleted clip and a new one that reused its name cannot share one.
      media.src = item.media === "audio"
        ? "/api/gallery/trash/" + encodeURIComponent(item.id) + "/poster?v=" + item.version
        : url;
      // The route is there but the drawing can fail on an odd file; an icon
      // beats a broken-image box.
      if (item.media === "audio") {
        media.addEventListener("error", function () { media.src = SONG_TILE; },
                               { once: true });
      }
    }
    media.alt = item.idea || t("Something deleted");
    tile.appendChild(media);
    var badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = t(item.media === "video" ? "▶ Video"
      : item.media === "audio" ? "🎵 Song" : "Picture");
    tile.appendChild(badge);
    tile.addEventListener("click", function () { openViewer(item, true); });
    return tile;
  }

  // --- choosing several at once -------------------------------------------

  function togglePick(id) {
    var at = chosen.indexOf(id);
    if (at === -1) chosen.push(id);
    else chosen.splice(at, 1);
    markChosen();
    refreshPicked();
  }

  // The ticks, from the list of ids. The same thing can be on screen twice - a
  // favourite picture is on Favourites and on Pictures - so this marks every
  // copy of it rather than only the tile they tapped.
  function markChosen() {
    Array.prototype.forEach.call(mineCard.querySelectorAll(".tile[data-item-id]"),
      function (tile) {
        tile.classList.toggle("chosen", chosen.indexOf(tile.dataset.itemId) !== -1);
      });
  }

  function refreshPicked() {
    var n = chosen.length;
    pickedCount.textContent =
      n === 0 ? t("Tap the ones you want")
              : n === 1 ? t("1 chosen") : t("{n} chosen", { n: n });

    var none = n === 0;
    if (armed === pickedDelete) disarm();  // the count changed; ask again
    pickedSave.setAttribute("aria-disabled", none ? "true" : "false");
    pickedDelete.disabled = none;
    pickedSave.href = none ? "#" : "/api/gallery/zip?ids=" + chosen.map(encodeURIComponent).join(",");
    pickedAll.textContent = (n && n === shown.length) ? t("Choose none") : t("Choose all");
    // Joining wants at least two videos and nothing else in the pick.
    var picks = chosenItems();
    var allVideo = picks.length >= 2 && picks.every(function (i) { return i.media === "video"; });
    pickedJoin.hidden = !allVideo;
    // Exactly two, both pictures: the "which of these four?" question.
    pickedCompare.hidden = !(picks.length === 2 &&
      picks.every(function (i) { return i.media === "image"; }));
  }

  function chosenItems() {
    return chosen.map(function (id) {
      return shownItems.filter(function (i) { return i.id === id; })[0];
    }).filter(Boolean);
  }

  // --- join clips into one film ---------------------------------------------
  // The title card is drawn here, on a canvas, with the page's own font and
  // the banner behind it - the server has no fonts and needs none.

  var SHAPES = { landscape: [1280, 704], portrait: [832, 1088], square: [960, 960] };
  var bannerImg = document.querySelector(".banner img");

  function drawTitleCard(canvas, title, w, h) {
    canvas.width = w; canvas.height = h;
    var c = canvas.getContext("2d");
    c.fillStyle = "#1b1035"; c.fillRect(0, 0, w, h);
    if (bannerImg && bannerImg.complete && bannerImg.naturalWidth) {
      // cover-fit the meadow
      var s = Math.max(w / bannerImg.naturalWidth, h / bannerImg.naturalHeight);
      var bw = bannerImg.naturalWidth * s, bh = bannerImg.naturalHeight * s;
      c.drawImage(bannerImg, (w - bw) / 2, (h - bh) * 0.7, bw, bh);
    }
    var g = c.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "rgba(27,16,53,0.15)"); g.addColorStop(0.5, "rgba(27,16,53,0.55)"); g.addColorStop(1, "rgba(27,16,53,0.85)");
    c.fillStyle = g; c.fillRect(0, 0, w, h);

    c.textAlign = "center"; c.textBaseline = "middle"; c.fillStyle = "#fff";
    c.shadowColor = "rgba(0,0,0,0.6)"; c.shadowBlur = 18; c.shadowOffsetY = 4;
    var small = Math.round(h * 0.055);
    c.font = "700 " + small + "px ui-rounded, -apple-system, system-ui, sans-serif";
    c.fillStyle = "#ffe9a8";
    c.fillText(t("{title} presents", { title: appTitle }), w / 2, h * 0.32);

    var text = (title || t("My Film")).trim();
    var big = Math.round(h * 0.13);
    c.fillStyle = "#fff";
    // shrink until it fits, then wrap onto two lines if it still does not
    var lines = [text];
    for (;;) {
      c.font = "800 " + big + "px ui-rounded, -apple-system, system-ui, sans-serif";
      if (c.measureText(text).width <= w * 0.86 || big <= h * 0.07) break;
      big -= 2;
    }
    if (c.measureText(text).width > w * 0.86) {
      var words = text.split(" "), a = "", b = "";
      words.forEach(function (word) {
        if (c.measureText(a + " " + word).width <= w * 0.86 || !a) a = (a ? a + " " : "") + word;
        else b = (b ? b + " " : "") + word;
      });
      lines = b ? [a, b] : [a];
    }
    lines.forEach(function (line, i) {
      c.fillText(line, w / 2, h * 0.55 + (i - (lines.length - 1) / 2) * big * 1.15);
    });
    c.shadowBlur = 0; c.shadowOffsetY = 0;
  }

  var joinShape = "landscape";
  function refreshTitlePreview() {
    var wh = SHAPES[joinShape] || SHAPES.landscape;
    // preview at half size; the real card is drawn full size on submit
    drawTitleCard(titlePreview, joinTitle.value, wh[0] / 2, wh[1] / 2);
  }
  joinTitle.addEventListener("input", refreshTitlePreview);

  function openJoin() {
    var picks = chosenItems();
    if (picks.length < 2) return;
    joinShape = picks[0].orientation || "landscape";
    joinSheet.hidden = false;
    lockPage();
    joinStatus.hidden = true;
    joinGo.disabled = false;
    joinNote.textContent =
      t("{n} videos, in the order you chose them. It'll open with a title card - give it a name!",
        { n: picks.length });
    refreshTitlePreview();
  }
  function closeJoin() {
    joinSheet.hidden = true;
    backToMine();
  }
  function joinGoNow() {
    var picks = chosenItems();
    if (picks.length < 2) return;
    joinGo.disabled = true;
    joinStatus.textContent = t("Joining your film... this takes a little while.");
    joinStatus.hidden = false;
    var wh = SHAPES[joinShape] || SHAPES.landscape;
    var card = document.createElement("canvas");
    drawTitleCard(card, joinTitle.value, wh[0], wh[1]);
    card.toBlob(function (blob) {
      var form = new FormData();
      form.append("ids", chosen.join(","));
      form.append("title", joinTitle.value.trim());
      form.append("card", new File([blob], "title.png", { type: "image/png" }));
      fetch("/api/gallery/join", { method: "POST", body: form })
        .then(readJSON)
        .then(function () {
          joinStatus.textContent = t("Done! It's at the top of your videos.");
          ding();
          setTimeout(function () {
            joinSheet.hidden = true;
            setChoosing(false);
            backToMine();
          }, 900);
        })
        .catch(function (err) {
          joinStatus.textContent = err.message;
          joinGo.disabled = false;
        });
    }, "image/png");
  }

  function setChoosing(on) {
    choosing = on;
    chosen = [];
    disarm();
    selectBtn.classList.toggle("is-on", on);
    selectBtn.textContent = on ? t("Cancel") : t("Choose");
    pickedBar.hidden = !on;
    mineCard.classList.toggle("choosing", on);   // room for the fixed bar
    markChoosable(on);
    markChosen();
    refreshPicked();
  }

  // The ticks only belong on the things they may actually choose: not the
  // characters row above the shelves, and not the trash.
  function markChoosable(on) {
    Array.prototype.forEach.call(
      mineCard.querySelectorAll(".mine-grid, .shelf[data-media] .strip"),
      function (box) { box.classList.toggle("choosing", on); });
  }

  function chooseAllOrNone() {
    var all = chosen.length === shown.length;
    // Only the ones they may actually choose: a family tile that is somebody
    // else's takes no tick, and `shown` is already just theirs.
    chosen = all ? [] : shown.slice();
    markChosen();
    refreshPicked();
  }

  function deleteChosen() {
    if (!chosen.length) return;
    disarm();
    var wasChosen = chosen.slice();
    postJSON("/api/gallery/delete", { ids: chosen })
      .then(function () {
        setChoosing(false);
        refreshMine();
        offerUndo(wasChosen);
      })
      .catch(function (err) {
        pickedCount.textContent = err.message;
      });
  }

  // Deleting asks in the button itself rather than in a panel underneath: the
  // eye stays on what was just tapped, and there is nothing to scroll to.
  // First tap arms it, second tap does it, and it disarms itself after a few
  // seconds or if they do anything else.
  var ARM_MS = 4000;
  var armed = null;   // the button currently asking
  var armedTimer = null;
  var armedLabel = "";

  function disarm() {
    clearTimeout(armedTimer);
    if (armed) {
      armed.textContent = armedLabel;
      armed.classList.remove("arming");
    }
    armed = null;
  }

  function arm(button, question) {
    if (armed === button) return true;   // second tap: go ahead
    disarm();
    armed = button;
    armedLabel = button.textContent;
    button.textContent = question;
    button.classList.add("arming");
    armedTimer = setTimeout(disarm, ARM_MS);
    return false;
  }

  function prettySize(bytes) {
    if (!bytes) return "";
    var mb = bytes / (1024 * 1024);
    return mb < 1 ? t("{n} KB", { n: Math.round(bytes / 1024) })
                  : t("{n} MB", { n: mb.toFixed(1) });
  }

  function prettyWhen(seconds) {
    var then = new Date(seconds * 1000);
    var mins = Math.round((Date.now() - then.getTime()) / 60000);
    if (mins < 1) return t("just now");
    if (mins < 60) {
      return t(mins === 1 ? "{n} minute ago" : "{n} minutes ago", { n: mins });
    }
    var hours = Math.round(mins / 60);
    if (hours < 24) {
      return t(hours === 1 ? "{n} hour ago" : "{n} hours ago", { n: hours });
    }
    return then.toLocaleDateString();
  }

  // overflow:hidden on body does not stop the page scrolling under a sheet in
  // iOS Safari; pinning the body does. Remember where they were so closing the
  // sheet lands them back on the same spot.
  var lockedAt = 0;
  var pageLocked = false;
  function lockPage() {
    if (pageLocked) return;
    pageLocked = true;
    lockedAt = window.pageYOffset || 0;
    document.body.style.position = "fixed";
    document.body.style.top = -lockedAt + "px";
    document.body.style.left = "0";
    document.body.style.right = "0";
    document.body.style.overflow = "hidden";
  }
  function unlockPage() {
    if (!pageLocked) return;
    pageLocked = false;
    document.body.style.position = "";
    document.body.style.top = "";
    document.body.style.left = "";
    document.body.style.right = "";
    document.body.style.overflow = "";
    window.scrollTo(0, lockedAt);
  }

  // Everything last fetched, so searching and the tag chips filter in the page
  // rather than going back to the server on every keystroke.
  var allItems = [];
  var allTags = [];
  var available = true;     // false if the gallery directory cannot be read
  var findText = "";        // what they have typed on the Gallery page
  var tagFilter = "";       // and which tag chip is on
  var pickFind = "";        // the picker sheet's own search, which is not theirs
  var pickOnly = null;      // and what it is allowed to show, if not everything

  function matches(item, text, tag) {
    if (tag && (item.tags || []).indexOf(tag) === -1) return false;
    if (!text) return true;
    var hay = ((item.name || "") + " " + (item.idea || "") + " " + (item.prompt || "") + " " +
               (item.tags || []).join(" ") + " " + (item.kind || "")).toLowerCase();
    // Every word has to appear somewhere: "blue dragon" should not match a
    // picture that is merely blue.
    return text.split(/\s+/).every(function (word) { return hay.indexOf(word) !== -1; });
  }

  // The picker sheet: every picture they could start something from, on the
  // same shelves, with its own search box. No choosing, no trash, no tags -
  // it is one tap and then gone.
  function paintShelves() {
    var items = allItems.filter(function (i) {
      return (!pickOnly || pickOnly(i)) && matches(i, pickFind, "");
    });
    sheetEmpty.textContent = pickFind
      ? t("Nothing matches that. Try another word!")
      : t("Nothing here yet! Go and make something.");
    sheetEmpty.hidden = items.length > 0;
    Array.prototype.forEach.call(shelves, function (shelf) {
      var on = items.filter(function (i) { return shelfMatch(shelf, i); });
      shelf.hidden = on.length === 0;
      shelf.querySelector(".count").textContent = on.length ? "(" + on.length + ")" : "";
      var into = shelf.querySelector(".grid");
      into.innerHTML = "";
      on.forEach(function (item) { into.appendChild(makeTile(item)); });
    });
  }

  function paintTags() {
    albumsRow.innerHTML = "";
    albumsRow.hidden = allTags.length === 0;
    if (!allTags.length) return;
    [""].concat(allTags).forEach(function (name) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "album-chip" + (tagFilter === name ? " is-on" : "");
      chip.textContent = name ? "#" + name : t("Everything");
      chip.addEventListener("click", function () {
        tagFilter = tagFilter === name ? "" : name;
        paintTags();
        paintMine();
      });
      albumsRow.appendChild(chip);
    });
  }

  // Tags are words they pick themselves, on one thing or on everything they have
  // chosen. A prompt() rather than a sheet of its own: they are typing a word,
  // and the ones already in use are on the chips right above them.
  function tagPicked() {
    if (!chosen.length) return;
    var tag = window.prompt(
      t("What tag should these get?") +
      (allTags.length
        ? t("\n\nAlready used: ") + allTags.map(function (tag) { return "#" + tag; }).join(", ")
        : ""),
      tagFilter || "");
    if (tag === null || !tag.trim()) return;
    var ids = chosen.slice();
    postJSON("/api/gallery/tag", { ids: ids, tag: tag.trim(), on: true })
      .then(function (data) {
        setChoosing(false);
        refreshMine();
        showToast(t(ids.length === 1 ? "{n} thing tagged “#{tag}”" : "{n} things tagged “#{tag}”",
                    { n: ids.length, tag: data.tag }), { ms: 3000 });
      })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 4000 }); });
  }

  // Everything the page needs out of one listing. Both surfaces read the same
  // `allItems`, so the page only ever asks the server once per change.
  function useListing(data) {
    allItems = data.items || [];
    allTags = data.tags || [];
    available = data.available !== false;
    if (tagFilter && allTags.indexOf(tagFilter) === -1) tagFilter = "";
    paintTags();
    paintMine();
  }

  // The card is painted from this on load and after anything that changes what
  // is in there. It deliberately leaves what is on screen alone if the fetch
  // fails: an empty card would look like loss.
  function refreshMine() {
    return fetch("/api/gallery")
      .then(readJSON)
      .then(function (data) { useListing(data); loadTrash(); })
      .catch(function () {});
  }

  // The Gallery is a page, so "back to the gallery" is closing whatever is over it
  // rather than opening anything.
  function backToMine() {
    closeGallery();
    refreshMine();
  }

  // While `picking` is set, tapping a tile hands the item to it instead of
  // opening the viewer, and the sheet says what it is for.
  var picking = null;
  var galleryTitle = document.getElementById("gallery-title");

  // The only thing this sheet is for now: pick a picture for something else.
  // It always opens with an empty search - whatever they last looked for on the
  // Gallery page has nothing to do with the picture they are picking here.
  // `only` narrows what is offered: the video slots take a clip as happily as
  // a picture, but starting a picture from one cannot, so that caller passes a
  // test and the shelves that come up empty simply do not appear.
  function openGallery(opts) {
    picking = (opts && opts.pick) || null;
    pickOnly = (opts && opts.only) || null;
    if (galleryTitle) galleryTitle.textContent = (opts && opts.title) || t("Pick a picture");
    sheet.hidden = false;
    viewer.hidden = true;
    sheetEmpty.hidden = true;
    if (choosing) setChoosing(false);
    pickFind = "";
    findBox.value = "";
    findClear.hidden = true;
    Array.prototype.forEach.call(shelves, function (shelf) {
      shelf.querySelector(".grid").innerHTML = "";
      shelf.hidden = true;
    });
    lockPage();

    fetch("/api/gallery")
      .then(readJSON)
      .then(function (data) { useListing(data); paintShelves(); })
      .catch(function () {
        sheetEmpty.textContent = t("Couldn't open your gallery right now. Try again!");
        sheetEmpty.hidden = false;
      });
  }

  var findBox = document.getElementById("find");
  var findClear = document.getElementById("find-clear");
  var mineFind = document.getElementById("mine-find");
  var mineFindClear = document.getElementById("mine-find-clear");
  var albumsRow = document.getElementById("albums");
  findBox.addEventListener("input", function () {
    pickFind = findBox.value.trim().toLowerCase();
    findClear.hidden = pickFind === "";
    paintShelves();
  });
  findClear.addEventListener("click", function () {
    findBox.value = "";
    pickFind = "";
    findClear.hidden = true;
    paintShelves();
    findBox.focus();
  });
  mineFind.addEventListener("input", function () {
    findText = mineFind.value.trim().toLowerCase();
    mineFindClear.hidden = findText === "";
    paintMine();
  });
  mineFindClear.addEventListener("click", function () {
    mineFind.value = "";
    findText = "";
    mineFindClear.hidden = true;
    paintMine();
    mineFind.focus();
  });

  function closeGallery() {
    disarm();
    picking = null;
    pickOnly = null;
    sheet.hidden = true;
    viewer.hidden = true;
    viewerMedia.innerHTML = "";   // stop any video that is playing
    unlockPage();
  }

  // Open the big viewer for a gallery id we only know by name - the four-up
  // grid has filenames, not the item records the gallery sheet builds.
  function openViewerById(id) {
    fetch("/api/gallery").then(readJSON).then(function (data) {
      var item = (data.items || []).filter(function (i) { return i.id === id; })[0];
      if (!item) return;
      lockPage();
      openViewer(item, false);
    }).catch(function () {});
  }

  // Their own name for a thing, saved as they stop typing rather than behind a
  // button they would have to notice.
  var nameTimer = null;
  viewerName.addEventListener("input", function () {
    if (!viewing) return;
    var id = viewing.id, value = viewerName.value;
    clearTimeout(nameTimer);
    nameTimer = setTimeout(function () {
      fetch("/api/gallery/" + encodeURIComponent(id) + "/name", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: value }),
      }).then(readJSON).then(function (data) {
        if (viewing && viewing.id === id) viewing.name = data.name;
        var cached = allItems.filter(function (i) { return i.id === id; })[0];
        if (cached) cached.name = data.name;
        refreshMine();
      }).catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 4000 }); });
    }, 700);
  });

  function paintViewerTags() {
    viewerTags.innerHTML = "";
    // Tags are theirs to add and remove. On somebody else's family item every
    // chip here is an editor, so the whole row goes.
    if (!viewing || viewingTrashed || viewing.mine === false) {
      viewerTags.hidden = true;
      return;
    }
    viewerTags.hidden = false;
    (viewing.tags || []).forEach(function (tag) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "tag-chip";
      chip.appendChild(document.createTextNode("#" + tag));
      var x = document.createElement("span");
      x.className = "x";
      x.textContent = "✕";
      chip.appendChild(x);
      chip.addEventListener("click", function () { changeTag(tag, false); });
      viewerTags.appendChild(chip);
    });
    var add = document.createElement("button");
    add.type = "button";
    add.className = "tag-chip tag-add";
    add.textContent = t("＋ Add a tag");
    add.addEventListener("click", function () {
      var tag = window.prompt(
        t("What tag?") + (allTags.length ? t("\n\nAlready used: ") +
          allTags.map(function (t) { return "#" + t; }).join(", ") : ""), "");
      if (tag && tag.trim()) changeTag(tag.trim(), true);
    });
    viewerTags.appendChild(add);
  }

  function changeTag(tag, on) {
    if (!viewing) return;
    var id = viewing.id;
    postJSON("/api/gallery/tag", { ids: [id], tag: tag, on: on })
      .then(function (data) {
        allTags = data.tags || allTags;
        return fetch("/api/gallery").then(readJSON);
      })
      .then(function (data) {
        allItems = data.items || allItems;
        allTags = data.tags || allTags;
        var fresh = allItems.filter(function (i) { return i.id === id; })[0];
        if (fresh && viewing && viewing.id === id) viewing.tags = fresh.tags;
        paintViewerTags();
        paintTags();
        paintMine();
      })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 4000 }); });
  }

  function openViewer(item, trashed) {
    viewing = item;
    viewingTrashed = !!trashed;
    // Where the Back button goes. Nearly always the Gallery page; the picker
    // only gets here when they tap somebody else's family tile in it, which
    // cannot be picked and so opens to be looked at.
    viewerFromPicker = !sheet.hidden;
    sheet.hidden = true;
    lockPage();
    viewer.hidden = false;
    disarm();
    viewer.scrollTop = 0;
    viewerLive.hidden = viewingTrashed;
    viewerTrashed.hidden = !viewingTrashed;
    viewerName.value = item.name || "";
    // Naming is the maker's: a family item keeps whatever they called it.
    viewerName.parentNode.hidden = viewingTrashed || item.mine === false;
    paintViewerTags();
    paintViewerMaker(item);

    var url = viewingTrashed
      ? "/api/gallery/trash/" + encodeURIComponent(item.id) + "/file?v=" + item.version
      : fileUrl(item);
    viewerMedia.innerHTML = "";
    var media;
    if (item.media === "audio") {
      // A song shows its waveform and plays underneath it, the same shape the
      // finished-song result uses.
      var song = document.createElement("div");
      song.className = "song";
      if (!viewingTrashed) {
        var art = document.createElement("img");
        art.className = "song-wave";
        art.alt = "";
        art.src = posterUrl(item);
        song.appendChild(art);
      }
      media = document.createElement("audio");
      media.controls = true;
      media.preload = "metadata";
      media.src = url;
      song.appendChild(media);
      viewerMedia.appendChild(song);
    } else {
      if (item.media === "video") {
        media = document.createElement("video");
        media.controls = true;
        media.playsInline = true;
        media.preload = "metadata";
        if (!viewingTrashed) media.poster = posterUrl(item);
      } else {
        media = document.createElement("img");
        media.alt = item.prompt || t("Something you made");
      }
      media.src = url;
      viewerMedia.appendChild(media);
    }

    if (item.media === "audio" && item.lyrics && item.lyrics.trim() === "[inst]") {
      viewerPrompt.textContent = (item.idea || item.prompt || "") +
        "  " + t("(music only - nobody sings on this one.)");
      viewerPrompt.classList.remove("none");
    } else if (item.prompt) {
      // Their own words in preference on a French page: `prompt` is the composed
      // one, which is English by construction because it is what ComfyUI was
      // handed, and "what you asked for" should be what they asked in.
      viewerPrompt.textContent =
        (I18N.lang === "en" ? "" : item.idea) || item.prompt;
      viewerPrompt.classList.remove("none");
      if (item.recovered) {
        viewerPrompt.textContent += "  " +
          t("(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)");
      }
    } else if (isUpload(item)) {
      viewerPrompt.textContent = item.source === "drawing"
        ? t("A drawing you made. Tap Animate this to bring it to life!")
        : item.source === "card"
          ? t("A card you made. Print it, or share it!")
          : t("A photo you added. Tap Animate this to bring it to life!");
      viewerPrompt.classList.add("none");
    } else {
      viewerPrompt.textContent =
        t("This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.");
      viewerPrompt.classList.add("none");
    }

    // The words, for a song. Shown as written - the [Verse] and [Chorus]
    // markers are how they read where they are in it.
    if (viewerLyrics) {
      var sung = item.media === "audio" && item.lyrics &&
                 item.lyrics.trim() && item.lyrics.trim() !== "[inst]";
      viewerLyrics.hidden = !sung;
      if (sung) viewerLyrics.querySelector(".lyric-sheet").textContent = item.lyrics.trim();
    }

    var facts = [prettyWhen(item.created)];
    if (item.duration) facts.push(t("{n} seconds long", { n: item.duration }));
    if (item.width && item.height) facts.push(item.width + " \u00d7 " + item.height);
    // A song has no shape. It was falling through to the orientation the card
    // happened to be set to, and telling them a song was "landscape".
    else if (item.orientation && item.media !== "audio") facts.push(t(item.orientation));
    if (item.bytes) facts.push(prettySize(item.bytes));
    viewerFacts.textContent = facts.join(" · ");

    viewerSave.href = fileUrl(item, "&download=1");
    viewerSave.setAttribute("download", item.id);
    viewerAnimate.hidden = item.media !== "image";
    // Only pictures make characters, and only until the cast list is full.
    viewerCast.hidden = item.media !== "image" || cast.length >= (castMax || 12);
    // Shown for every video, even where the browser cannot record. Hiding it
    // made "nothing happens" the experience on a plain-http origin, where
    // getUserMedia does not exist; the sheet now opens and says so, and offers
    // to take a sound from their files instead.
    viewerVoice.hidden = item.media !== "video";
    viewerSound.hidden = item.media !== "video";
    viewerFrame.hidden = item.media !== "video";
    viewerNext.hidden = item.media !== "video";
    viewerSmooth.hidden = item.media !== "video";
    viewerSlow.hidden = item.media !== "video";
    viewerLoop.hidden = item.media !== "video";
    // Four times an already-huge picture is four hundred megapixels, and both
    // kinds of sticker would come back as one flat frame with no see-through
    // bits - the upscaler reads RGB and hands back RGB.
    viewerHuge.hidden = item.media !== "image" || item.kind === "huge" ||
      item.kind === "sticker" || item.kind === "loop";
    // The three Klein edits. Every picture of theirs can be changed - one they
    // made, a photo, a drawing, a comic page, one they have already changed -
    // except the two kinds of sticker, which would come back with their
    // see-through bits filled in, and a huge one, which is four megapixels
    // the model would only shrink again.
    var editable = item.media === "image" && item.kind !== "sticker" &&
      item.kind !== "loop" && item.kind !== "huge";
    // "Turn it into..." wants exactly the same picture the three edits do -
    // it *is* the edit graph, with a sentence of ours in the box.
    viewerRestyle.hidden = !editable;
    viewerChange.hidden = !editable;
    viewerOutside.hidden = !editable;
    viewerFix.hidden = !editable;
    // A sticker is a picture with its background cut out, so there is nothing
    // to cut out of one - and nothing to cut out of a comic page either. A
    // moving sticker is a sticker too, and cutting one out would quietly throw
    // away every frame but the first.
    viewerSticker.hidden = item.media !== "image" ||
      item.kind === "sticker" || item.kind === "loop" || item.kind === "comic";
    viewer.querySelector(".viewer-again").hidden = !canRemake(item);
    // Same words, same seed: a variation on *this* picture rather than a new
    // one that merely matches the description. Only where a seed was recorded.
    // An edit's "but..." is the change sheet again on the picture it was made
    // from, with their words and the same seed - so a word changed gives a
    // variation on this one rather than an unrelated attempt.
    // ...and a restyled picture's "but..." is the chips again on the picture
    // it came from, with the same chip lit and the same seed.
    viewerTweak.hidden = item.kind === "restyle"
      ? !item.restyle_of
      : isEdit(item)
        ? (item.kind !== "edit" || !item.edit_of)
        : (!canRemake(item) || !item.seed && item.seed !== 0);
    viewer.querySelector(".viewer-draw").hidden = item.media !== "image";
    viewer.querySelector(".viewer-print").hidden = item.media !== "image";
    // A song has no picture in it to put across the top of the page.
    viewer.querySelector(".viewer-banner").hidden = item.media === "audio";
    // Only for a picture, and only once there is somebody to be: on a
    // one-child installation this is a second name for an icon nobody sees.
    viewer.querySelector(".viewer-face").hidden =
      item.media !== "image" || !me || !meChip || meChip.hidden;
    viewer.querySelector(".viewer-card").hidden = item.media !== "image" || (isUpload(item) && item.source === "card");
    viewerShare.hidden = !canShareFiles;
    setFavButton(!!item.favourite);

    // "Show the family" is theirs to press, and only once there is a family to
    // show it to: with one profile this button does not exist, exactly like
    // the picker and the header chip.
    if (viewerFamily) {
      viewerFamily.hidden = !severalWho || item.mine === false;
      setFamilyButton(!!item.family);
    }

    // Somebody else's, off the family shelf. They can look at it, save it,
    // share it and print it; everything that would change it or make something
    // new out of it belongs to whoever made it - and the server refuses all of
    // those anyway, so leaving the buttons up would only be a promise the app
    // cannot keep.
    if (item.mine === false) {
      [viewerFav, viewerDelete, viewerAnimate, viewerCast, viewerVoice,
       viewerSound, viewerFrame, viewerNext, viewerSticker, viewerTweak,
       viewerSmooth, viewerSlow, viewerLoop, viewerHuge,
       viewerRestyle, viewerChange, viewerOutside, viewerFix,
       viewer.querySelector(".viewer-again"), viewer.querySelector(".viewer-draw"),
       viewer.querySelector(".viewer-banner"), viewer.querySelector(".viewer-face"),
       viewer.querySelector(".viewer-card")].forEach(function (button) {
        if (button) button.hidden = true;
      });
    }
  }

  // Whose it is, said in the viewer as well as on the tile - the tile badge is
  // thirty pixels wide and they may well have scrolled past it.
  function paintViewerMaker(item) {
    if (!viewerMaker) return;
    var who = item.mine === false ? makerOf(item) : null;
    viewerMaker.hidden = !who;
    // "What you asked for" over somebody else's words is the same mistake the
    // face is here to prevent, one heading further down.
    if (viewerAsked) {
      viewerAsked.textContent = who ? t("What {name} asked for", { name: who.name })
                                    : t("What you asked for");
    }
    if (!who) return;
    faceInto(viewerMaker.querySelector(".maker-face"), who);
    viewerMaker.querySelector(".maker-name").textContent = t("{name} made this", { name: who.name });
  }

  function setFavButton(on) {
    viewerFav.textContent = on ? t("⭐ Favourite") : t("☆ Favourite");
    viewerFav.classList.toggle("is-on", on);
  }

  function setFamilyButton(on) {
    viewerFamily.textContent = on
      ? t("👨‍👩‍👧 Hide from the family")
      : t("👨‍👩‍👧 Show the family");
    viewerFamily.classList.toggle("is-on", on);
  }

  // Not armed, unlike delete: nothing is lost either way and they can put it
  // back with the same button, so a second tap would only be in the way.
  function toggleFamily() {
    if (!viewing || viewingTrashed || viewing.mine === false) return;
    var on = !viewing.family;
    setFamilyButton(on);   // optimistic; put back on failure
    fetch("/api/gallery/" + encodeURIComponent(viewing.id) + "/family", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: on })
    })
      .then(readJSON)
      .then(function () {
        viewing.family = on;
        showToast(on
          ? t("Everyone can see this one now! 👨‍👩‍👧")
          : t("Back to just you."), { ms: 3000 });
        refreshMine();
      })
      .catch(function () { setFamilyButton(!on); });
  }

  function toggleFavourite() {
    if (!viewing || viewingTrashed) return;
    var on = !viewing.favourite;
    setFavButton(on);   // optimistic; put back on failure
    fetch("/api/gallery/" + encodeURIComponent(viewing.id) + "/favourite", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: on })
    })
      .then(readJSON)
      .then(function () { viewing.favourite = on; refreshMine(); })
      .catch(function () { setFavButton(!on); });
  }

  function restoreViewing() {
    if (!viewing || !viewingTrashed) return;
    fetch("/api/gallery/trash/" + encodeURIComponent(viewing.id) + "/restore", { method: "POST" })
      .then(readJSON)
      .then(function () { viewing = null; backToMine(); })
      .catch(function (err) { viewerFacts.textContent = err.message; });
  }

  function destroyViewing() {
    if (!viewing || !viewingTrashed) return;
    disarm();
    fetch("/api/gallery/trash/" + encodeURIComponent(viewing.id), { method: "DELETE" })
      .then(readJSON)
      .then(function () { viewing = null; backToMine(); })
      .catch(function (err) { viewerFacts.textContent = err.message; });
  }

  // Everything needed to make another one like it is in the sidecar: their own
  // words (not the composed prompt, or the style phrases would double up), the
  // dropdown choices, the shape and the length.
  function makeAnother(item) {
    // A song is neither a picture nor a video. This was a two-way pick that
    // predates the music card, so every song they asked for again landed on the
    // video card - with their lyrics nowhere and a shape it has no use for.
    var card = item.media === "audio" ? cards.music
             : item.media === "image" ? cards.image
             : cards.video;
    // A parent can switch a maker off, and everything made with it stays in
    // their gallery, so the card it came from may not be there any more.
    if (!card) {
      showToast(t("That one's turned off just now."), { ms: 4000 });
      return;
    }
    closeGallery();

    if (card === cards.video) setMode(item.kind === "i2v" ? "i2v" : "t2v");
    // Which chip it was, **before** the length: setSoundKind re-applies that
    // kind's own bounds to the slider, so doing it afterwards would move the
    // handle they are being shown. `sound_kind` is what new sidecars carry;
    // falling back to the job kind covers the ones written before it existed
    // and the songs, whose job kind is still "music".
    if (card === cards.music) {
      setSoundKindPicked(card, item.sound_kind || item.kind || "song");
    }
    // A length in seconds, on the video slider or the song one.
    if (item.duration) setSeconds(card, item.duration);
    // A song has no shape.
    if (item.orientation && item.media !== "audio") setOrientation(card, item.orientation);
    if (card.kindPicks && card.kindPicks.length) {
      setCutout(card, !!item.cutout);
      Array.prototype.forEach.call(card.kindPicks, function (b) {
        var on = (b.dataset.cutout === "1") === !!item.cutout;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-checked", on ? "true" : "false");
      });
    }
    showTab(TAB_FOR_KIND[item.kind] || card.kind);
    card.textarea.value = item.idea || item.prompt || "";
    if (card.syncClear) card.syncClear();
    if (card.rememberText) card.rememberText();
    // The line they asked for out loud. It is not part of the description, so
    // without this the speech box came back empty and the character said
    // nothing the second time round.
    if (card.say) {
      card.say.value = item.said || "";
      card.say.dispatchEvent(new Event("input"));
    }
    // The words that get sung, and whether anybody sings them: the sidecar
    // keeps "[inst]" for music with nobody on it, which is the toggle off.
    if (card.lyrics) {
      var words = (item.lyrics || "").trim();
      var sung = !!words && words !== "[inst]";
      card.lyrics.value = sung ? words : "";
      keep("lyrics:" + card.kind, card.lyrics.value);
      card.lyrics.dispatchEvent(new Event("input"));
      setSingingPicked(card, sung);
    }
    applyStyles(card, item.styles || {});
    if (card.helperMsg) {
      card.helperMsg.textContent = t("Same as before - change anything you like, then go!");
      card.helperMsg.hidden = false;
    }
    card.el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function deleteViewing() {
    if (!viewing) return;
    var id = viewing.id;
    disarm();

    fetch("/api/gallery/" + encodeURIComponent(id), { method: "DELETE" })
      .then(readJSON)
      .then(function () {
        viewing = null;
        backToMine();
        offerUndo([id]);
      })
      .catch(function (err) {
        viewerFacts.textContent = err.message;
      });
  }

  // --- the Gallery page ------------------------------------------------------
  // Two views over the same listing. In groups is how they look for a kind of
  // thing - "where are my songs" - and it is what this card always was, a
  // sideways shelf each. Everything is one grid, newest first, for "the one I
  // made just now", with the kind on every tile instead of in a heading. Both
  // are the page itself rather than a sheet behind a button: what they have made
  // is the point of the tab, and a button in front of it was one tap and one
  // decision too many.

  var VIEWS = ["groups", "all"];
  var SORTS = {
    new: function (a, b) { return (b.created || 0) - (a.created || 0); },
    old: function (a, b) { return (a.created || 0) - (b.created || 0); },
    // Favourites first, newest first inside each half.
    fav: function (a, b) {
      if (!!a.favourite !== !!b.favourite) return a.favourite ? -1 : 1;
      return (b.created || 0) - (a.created || 0);
    },
    // The shelves, flattened: the same grouping they see in the other view.
    kind: function (a, b) {
      var left = SHELF_ORDER.indexOf(homeOf(a));
      var right = SHELF_ORDER.indexOf(homeOf(b));
      if (left !== right) return left - right;
      return (b.created || 0) - (a.created || 0);
    },
  };

  // Remembered like the tab is, so the way they like looking at their things is
  // how they find them next time.
  var mineView = recall("mine-view");
  var mineSort = recall("mine-sort");
  // Everything is the default: one grid of all of it is what "my stuff"
  // means to them; the shelves are the way to look for a kind of thing.
  if (VIEWS.indexOf(mineView) === -1) mineView = "all";
  if (!SORTS[mineSort]) mineSort = "new";
  pickIn(mineCard.querySelectorAll(".view-pick"), "view", mineView);
  pickIn(mineCard.querySelectorAll(".sort-pick"), "sort", mineSort);

  wireChoice(mineCard.querySelectorAll(".view-pick"), function (btn) {
    mineView = VIEWS.indexOf(btn.dataset.view) === -1 ? "all" : btn.dataset.view;
    keep("mine-view", mineView);
    paintMine();
  });
  wireChoice(mineCard.querySelectorAll(".sort-pick"), function (btn) {
    mineSort = SORTS[btn.dataset.sort] ? btn.dataset.sort : "new";
    keep("mine-sort", mineSort);
    paintMine();
  });

  function paintMine() {
    var empty = !available || allItems.length === 0;
    mineEmpty.hidden = !empty;
    mineNote.hidden = empty;
    // Nothing in there is nothing to search, sort or choose from.
    mineSettings.hidden = empty;
    mineTools.hidden = empty;
    if (empty) {
      albumsRow.hidden = true;
      mineNone.hidden = true;
      mineGrid.hidden = true;
      mineGrid.innerHTML = "";
      Array.prototype.forEach.call(mineShelves, function (shelf) {
        shelf.hidden = true;
        shelf.querySelector(".strip").innerHTML = "";
      });
      return;
    }

    // Theirs, not the family's: a sister's shared video is not something this
    // child has made, and the sentence says "you've made".
    var ownCount = allItems.filter(function (i) { return i.mine !== false; }).length;
    mineNote.textContent =
      ownCount === 0
        ? t("Nothing of yours yet - but there's something on the family shelf!")
        : ownCount === 1
          ? t("You've made 1 thing so far.")
          : t("You've made {n} things so far.", { n: ownCount });

    var items = allItems.filter(function (i) { return matches(i, findText, tagFilter); });
    // An order only means something in one long list; the shelves have one.
    mineOrder.hidden = mineView !== "all";
    selectBtn.hidden = items.length === 0;
    mineNone.hidden = items.length > 0;

    // Only the view they are looking at is painted: "Choose all" should mean
    // what is on screen, and twice the tiles is twice the pictures to decode.
    if (mineView === "all") {
      Array.prototype.forEach.call(mineShelves, function (shelf) {
        shelf.hidden = true;
        shelf.querySelector(".strip").innerHTML = "";
      });
      items = items.slice().sort(SORTS[mineSort] || SORTS.new);
      mineGrid.innerHTML = "";
      items.forEach(function (item) { mineGrid.appendChild(makeTile(item)); });
      mineGrid.hidden = items.length === 0;
    } else {
      mineGrid.hidden = true;
      mineGrid.innerHTML = "";
      Array.prototype.forEach.call(mineShelves, function (shelf) {
        var on = items.filter(function (i) { return shelfMatch(shelf, i); });
        shelf.hidden = on.length === 0;
        shelf.querySelector(".count").textContent = on.length ? "(" + on.length + ")" : "";
        var strip = shelf.querySelector(".strip");
        strip.innerHTML = "";
        on.forEach(function (item) { strip.appendChild(makeTile(item)); });
      });
    }

    // "Choose all" means all of theirs. A family item cannot be chosen at all -
    // see makeTile - so counting it here would leave the button stuck saying
    // "Choose all" after they had already chosen everything they can.
    shown = items.filter(function (i) { return i.mine !== false; })
                 .map(function (i) { return i.id; });
    shownItems = items;
    // Tiles are new objects every repaint, so the ticks have to go back on.
    if (choosing) { markChoosable(true); markChosen(); refreshPicked(); }
  }

  refreshMine();

  // --- make a card ----------------------------------------------------------
  // A picture on a coloured card with their message under it, drawn on a canvas
  // here and saved into the gallery as an upload, so it can be printed or
  // shared like anything else. Sized for an A5-ish print: 1240 wide.

  var cardSheet = document.getElementById("cardmaker");
  var cardMessage = cardSheet.querySelector(".card-message");
  var cardPreview = cardSheet.querySelector(".card-preview");
  var cardStatus = cardSheet.querySelector(".card-status");
  var cardColours = cardSheet.querySelector(".card-colours");
  var CARD_COLOURS = [["#ffe3ec", "#c2185b"], ["#e3f2ff", "#1565c0"], ["#fff6d6", "#a05a00"], ["#e6f7e9", "#2e7d32"], ["#f0e6ff", "#6a1b9a"]];
  var cardColour = CARD_COLOURS[0];
  var cardBase = null;      // the picture
  var cardItem = null;

  CARD_COLOURS.forEach(function (pair, i) {
    var sw = document.createElement("button");
    sw.type = "button";
    sw.className = "swatch" + (i === 0 ? " is-on" : "");
    sw.style.background = pair[0];
    sw.setAttribute("aria-label", t("Card colour {n}", { n: i + 1 }));
    sw.addEventListener("click", function () {
      cardColour = pair;
      Array.prototype.forEach.call(cardColours.children, function (o) { o.classList.toggle("is-on", o === sw); });
      drawCard(cardPreview, 620);
    });
    cardColours.appendChild(sw);
  });
  cardMessage.addEventListener("input", function () { drawCard(cardPreview, 620); });

  function drawCard(canvas, W) {
    if (!cardBase) return;
    var pad = Math.round(W * 0.06);
    var imgW = W - pad * 2;
    var imgH = Math.round(imgW * cardBase.naturalHeight / cardBase.naturalWidth);
    var band = Math.round(W * 0.34);
    var H = pad + imgH + band;
    canvas.width = W; canvas.height = H;
    var c = canvas.getContext("2d");
    c.fillStyle = cardColour[0]; c.fillRect(0, 0, W, H);
    // a dotted border, like a real card
    c.strokeStyle = cardColour[1]; c.lineWidth = Math.max(2, W * 0.006); c.setLineDash([W * 0.02, W * 0.012]);
    c.strokeRect(pad * 0.45, pad * 0.45, W - pad * 0.9, H - pad * 0.9); c.setLineDash([]);
    // the picture with rounded corners and a soft shadow
    c.save();
    c.shadowColor = "rgba(0,0,0,0.25)"; c.shadowBlur = W * 0.03; c.shadowOffsetY = W * 0.01;
    var r = W * 0.03;
    c.beginPath();
    c.moveTo(pad + r, pad); c.arcTo(pad + imgW, pad, pad + imgW, pad + imgH, r); c.arcTo(pad + imgW, pad + imgH, pad, pad + imgH, r);
    c.arcTo(pad, pad + imgH, pad, pad, r); c.arcTo(pad, pad, pad + imgW, pad, r); c.closePath();
    c.fillStyle = "#fff"; c.fill(); c.shadowBlur = 0; c.shadowOffsetY = 0; c.clip();
    c.drawImage(cardBase, pad, pad, imgW, imgH);
    c.restore();
    // the message, wrapped, as big as fits
    var text = cardMessage.value.trim() || t("Made for you!");
    c.fillStyle = cardColour[1]; c.textAlign = "center"; c.textBaseline = "middle";
    var size = Math.round(W * 0.085), lines;
    for (;;) {
      c.font = "800 " + size + "px ui-rounded, -apple-system, system-ui, sans-serif";
      lines = wrap(c, text, imgW * 0.94);
      if (lines.length * size * 1.2 <= band * 0.7 || size <= W * 0.035) break;
      size -= 2;
    }
    var top = pad + imgH + band / 2 - (lines.length - 1) * size * 0.6;
    lines.forEach(function (line, i) { c.fillText(line, W / 2, top + i * size * 1.2); });
    c.font = "600 " + Math.round(W * 0.028) + "px ui-rounded, -apple-system, system-ui, sans-serif";
    c.fillStyle = "rgba(0,0,0,0.45)";
    c.fillText(t("made at {title}", { title: appTitle }), W / 2, H - pad * 0.85);
  }

  function wrap(c, text, maxWidth) {
    var words = text.split(/\s+/), lines = [], line = "";
    words.forEach(function (w) {
      var test = line ? line + " " + w : w;
      if (c.measureText(test).width <= maxWidth || !line) line = test;
      else { lines.push(line); line = w; }
    });
    if (line) lines.push(line);
    return lines.slice(0, 4);
  }

  function openCardMaker(item) {
    cardItem = item;
    closeGallery();
    cardSheet.hidden = false;
    lockPage();
    cardStatus.hidden = true;
    cardMessage.value = "";
    var img = new Image();
    img.onload = function () { cardBase = img; drawCard(cardPreview, 620); };
    img.src = fileUrl(item);
  }
  function closeCardMaker() {
    cardSheet.hidden = true;
    backToMine();
  }
  function saveCard() {
    if (!cardBase) return;
    var button = cardSheet.querySelector('[data-action="card-go"]');
    button.disabled = true;
    cardStatus.textContent = t("Saving your card...");
    cardStatus.hidden = false;
    var full = document.createElement("canvas");
    drawCard(full, 1240);
    full.toBlob(function (blob) {
      var form = new FormData();
      form.append("photo", new File([blob], "card.png", { type: "image/png" }));
      form.append("source", "card");
      form.append("message", cardMessage.value.trim());
      fetch("/api/upload", { method: "POST", body: form })
        .then(readJSON)
        .then(function () {
          cardStatus.textContent = t("Saved! It's in Photos & drawings - open it to print or share.");
          ding();
          setTimeout(function () { cardSheet.hidden = true; backToMine(); }, 1100);
        })
        .catch(function (err) { cardStatus.textContent = err.message; })
        .then(function () { button.disabled = false; });
    }, "image/png");
  }

  // --- draw one -------------------------------------------------------------
  // A finger-or-pencil canvas that feeds the same upload path a photo does, so
  // the vision helper and "Animate it" work on their drawing unchanged.

  var drawSheet = document.getElementById("draw");
  var canvas = drawSheet.querySelector(".draw-canvas");
  var canvasWrap = drawSheet.querySelector(".canvas-wrap");
  var palette = drawSheet.querySelector(".palette");
  var ctx = canvas.getContext("2d");
  var COLOURS = ["#1b1b1b", "#e63946", "#f77f00", "#ffd23f", "#2a9d8f", "#4361ee", "#9b5de5", "#ff8fd0", "#8d5524", "#ffffff"];
  var colour = COLOURS[0];
  var brush = 14;
  var erasing = false;
  var drawing = false;
  var undoStack = [];
  var lastPoint = null;
  var baseImage = null;     // a gallery picture being drawn on, if any
  var canvasAspect = null;  // width / height to keep when a base picture is set
  var stamp = null;         // the emoji the next tap will place

  // "Fix just this bit" borrows this pad. What they paint is a *mask*, so two
  // canvases are painted in step: the visible one gets a see-through pink so
  // they can see their picture through what they are covering, and an offscreen one
  // gets solid white on black, which is what the server sends to ComfyUI. The
  // overlay cannot be the mask - it has their picture underneath it.
  var maskFor = null;            // the picture being fixed, or null for drawing
  var maskCanvas = document.createElement("canvas");
  var maskCtx = maskCanvas.getContext("2d");
  var maskPainted = false;
  var maskUndo = [];
  var maskSay = document.getElementById("mask-say");
  var maskWords = drawSheet.querySelector(".mask-words");
  var MASK_PAINT = "rgba(255, 60, 160, 0.45)";

  var STAMPS = ["⭐", "❤️", "🌸", "🌈", "🦋", "🐱", "🐶", "🌞", "🎈", "🍦", "👑", "🚀"];
  var stampsRow = drawSheet.querySelector(".stamps");
  STAMPS.forEach(function (emoji) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "stamp";
    b.textContent = emoji;
    b.setAttribute("aria-label", t("Stamp {emoji}", { emoji: emoji }));
    b.addEventListener("click", function () {
      stamp = (stamp === emoji) ? null : emoji;
      Array.prototype.forEach.call(stampsRow.children, function (o) { o.classList.toggle("is-on", o.textContent === stamp); });
      if (stamp) setEraser(false);
    });
    stampsRow.appendChild(b);
  });
  function clearStamp() {
    stamp = null;
    Array.prototype.forEach.call(stampsRow.children, function (o) { o.classList.remove("is-on"); });
  }

  COLOURS.forEach(function (c, i) {
    var sw = document.createElement("button");
    sw.type = "button";
    sw.className = "swatch" + (i === 0 ? " is-on" : "");
    sw.style.background = c;
    sw.setAttribute("aria-label", t("Colour {n}", { n: i + 1 }));
    sw.addEventListener("click", function () {
      colour = c;
      setEraser(false);
      clearStamp();
      Array.prototype.forEach.call(palette.children, function (o) { o.classList.toggle("is-on", o === sw); });
    });
    palette.appendChild(sw);
  });
  Array.prototype.forEach.call(drawSheet.querySelectorAll(".brush"), function (b) {
    b.addEventListener("click", function () {
      brush = parseInt(b.dataset.size, 10) || 14;
      Array.prototype.forEach.call(drawSheet.querySelectorAll(".brush"), function (o) { o.classList.toggle("is-on", o === b); });
    });
  });

  function setEraser(on) {
    erasing = on;
    if (on) clearStamp();
    drawSheet.querySelector(".eraser").classList.toggle("is-on", on);
  }

  function sizeCanvas() {
    // Match the CSS box at device resolution so lines are crisp on Retina.
    // With a base picture the canvas keeps that picture's shape inside the
    // box, so nothing is stretched and the export is the picture's shape.
    var rect = canvasWrap.getBoundingClientRect();
    var cssW = rect.width, cssH = rect.height;
    if (canvasAspect) {
      if (cssW / cssH > canvasAspect) cssW = cssH * canvasAspect;
      else cssH = cssW / canvasAspect;
    }
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    var dpr = window.devicePixelRatio || 1;
    var keep = canvas.width ? ctx.getImageData(0, 0, canvas.width, canvas.height) : null;
    canvas.width = Math.max(1, Math.round(cssW * dpr));
    canvas.height = Math.max(1, Math.round(cssH * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (maskFor) {
      maskCanvas.width = canvas.width;
      maskCanvas.height = canvas.height;
      maskCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      maskCtx.lineCap = "round";
      maskCtx.lineJoin = "round";
      maskCtx.fillStyle = "#000";
      maskCtx.fillRect(0, 0, cssW, cssH);
      maskCtx.fillStyle = maskCtx.strokeStyle = "#fff";
      maskPainted = false;
    }
    paintBase(cssW, cssH);
    if (keep) { try { ctx.putImageData(keep, 0, 0); } catch (e) { /* size changed; start clean */ } }
  }

  function paintBase(cssW, cssH) {
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cssW, cssH);
    if (baseImage) ctx.drawImage(baseImage, 0, 0, cssW, cssH);
  }

  function drawClear(remember) {
    if (remember) pushUndo();
    var dpr = window.devicePixelRatio || 1;
    paintBase(canvas.width / dpr, canvas.height / dpr);   // "start again" keeps the picture
    if (maskFor) {
      maskCtx.fillStyle = "#000";
      maskCtx.fillRect(0, 0, maskCanvas.width / dpr, maskCanvas.height / dpr);
      maskCtx.fillStyle = "#fff";
      maskPainted = false;
    }
  }

  function pushUndo() {
    try {
      undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
      if (undoStack.length > 20) undoStack.shift();
      // The mask is a second canvas painted in step, so undo has to move both
      // or a stroke they took back would still be in what the server is sent.
      if (maskFor) {
        maskUndo.push(maskCtx.getImageData(0, 0, maskCanvas.width, maskCanvas.height));
        if (maskUndo.length > 20) maskUndo.shift();
      }
    } catch (e) { /* out of memory on a huge canvas: undo just gets shorter */ }
  }

  function drawUndo() {
    var prev = undoStack.pop();
    if (prev) ctx.putImageData(prev, 0, 0);
    var prevMask = maskUndo.pop();
    if (prevMask) maskCtx.putImageData(prevMask, 0, 0);
  }

  function pointFrom(event) {
    var rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top,
             p: (event.pressure && event.pointerType === "pen") ? event.pressure : 1 };
  }

  canvas.addEventListener("pointerdown", function (event) {
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    pushUndo();
    if (stamp) {
      // A stamp is one tap, not a stroke.
      var at = pointFrom(event);
      ctx.font = (brush * 3.2) + "px serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(stamp, at.x, at.y);
      return;
    }
    drawing = true;
    lastPoint = pointFrom(event);
    // A tap with no movement still leaves a dot.
    ctx.beginPath();
    ctx.fillStyle = erasing ? "#fff" : (maskFor ? MASK_PAINT : colour);
    ctx.arc(lastPoint.x, lastPoint.y, (brush * lastPoint.p) / 2, 0, Math.PI * 2);
    ctx.fill();
    if (maskFor) {
      maskCtx.beginPath();
      maskCtx.fillStyle = erasing ? "#000" : "#fff";
      maskCtx.arc(lastPoint.x, lastPoint.y, (brush * lastPoint.p) / 2, 0, Math.PI * 2);
      maskCtx.fill();
      if (!erasing) maskPainted = true;
    }
  });
  canvas.addEventListener("pointermove", function (event) {
    if (!drawing) return;
    event.preventDefault();
    var pt = pointFrom(event);
    ctx.strokeStyle = erasing ? "#fff" : (maskFor ? MASK_PAINT : colour);
    ctx.lineWidth = brush * pt.p;
    ctx.beginPath();
    ctx.moveTo(lastPoint.x, lastPoint.y);
    ctx.lineTo(pt.x, pt.y);
    ctx.stroke();
    if (maskFor) {
      maskCtx.strokeStyle = erasing ? "#000" : "#fff";
      maskCtx.lineWidth = brush * pt.p;
      maskCtx.beginPath();
      maskCtx.moveTo(lastPoint.x, lastPoint.y);
      maskCtx.lineTo(pt.x, pt.y);
      maskCtx.stroke();
      if (!erasing) maskPainted = true;
    }
    lastPoint = pt;
  });
  function endStroke() { drawing = false; lastPoint = null; }
  canvas.addEventListener("pointerup", endStroke);
  canvas.addEventListener("pointercancel", endStroke);

  function openDraw(baseUrl, fixing) {
    drawSheet.hidden = false;
    lockPage();
    undoStack = [];
    maskUndo = [];
    setEraser(false);
    clearStamp();
    // Mask mode: the colours, the stamps and "Use my drawing" all go away,
    // because none of them mean anything when what they are painting is a
    // where-to-change rather than a picture. One thick brush is left, which is
    // the only choice that still does something.
    maskFor = fixing || null;
    brush = maskFor ? 30 : 14;
    Array.prototype.forEach.call(drawSheet.querySelectorAll(".brush"), function (o) {
      o.classList.toggle("is-on", parseInt(o.dataset.size, 10) === brush);
    });
    drawSheet.classList.toggle("masking", !!maskFor);
    drawSheet.querySelector("h2").textContent =
      maskFor ? t("🩹 Fix just this bit") : t("Draw something");
    drawSheet.querySelector('[data-action="use-drawing"]').hidden = !!maskFor;
    drawSheet.querySelector('[data-action="use-mask"]').hidden = !maskFor;
    maskWords.hidden = !maskFor;
    if (maskFor) maskSay.value = "";
    drawSheet.querySelector(".draw-note").innerHTML = maskFor
      ? t("Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.")
      : t("Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.");
    baseImage = null;
    canvasAspect = null;
    canvas.style.width = "";
    canvas.style.height = "";
    if (!baseUrl) {
      // Size after it is visible, otherwise the box measures 0x0.
      requestAnimationFrame(function () { sizeCanvas(); drawClear(false); });
      return;
    }
    var img = new Image();
    img.onload = function () {
      baseImage = img;
      canvasAspect = img.naturalWidth / img.naturalHeight;
      requestAnimationFrame(function () { sizeCanvas(); drawClear(false); });
    };
    img.onerror = function () { requestAnimationFrame(function () { sizeCanvas(); drawClear(false); }); };
    img.src = baseUrl;
  }
  function closeDraw() {
    drawSheet.hidden = true;
    maskFor = null;
    maskUndo = [];
    unlockPage();
  }
  window.addEventListener("resize", function () { if (!drawSheet.hidden) sizeCanvas(); });

  function useDrawing() {
    var button = drawSheet.querySelector('[data-action="use-drawing"]');
    button.disabled = true;
    button.textContent = "Sending...";
    canvas.toBlob(function (blob) {
      var form = new FormData();
      form.append("photo", new File([blob], "my-drawing.png", { type: "image/png" }));
      form.append("source", "drawing");
      fetch("/api/upload", { method: "POST", body: form })
        .then(readJSON)
        .then(function (data) {
          closeDraw();
          if (data.orientation) setOrientation(video, data.orientation);
          pickSource({ galleryId: data.gallery_id }, data.preview_url);
          refreshMine();
          video.helperMsg.textContent = t("Your drawing is ready! Tap the helper to get a script for it, or say what should happen.");
          video.helperMsg.hidden = false;
        })
        .catch(function (err) {
          drawSheet.querySelector(".draw-note").textContent = err.message;
        })
        .then(function () {
          button.disabled = false;
          button.textContent = t("Use my drawing");
        });
    }, "image/png");
  }

  // --- someone to talk to ---------------------------------------------------
  // A helper backed by whatever Ollama has. Deliberately not streamed: the
  // whole reply is checked on the server before any of it is shown, and a
  // streamed reply is on screen before a filter could have looked at it. The
  // cost is a few seconds of "thinking", which is why there is an animation.
  //
  // The conversation lives in this browser. The transcript also lives on the
  // server, where their grown-ups can read it - the helper says so if they ask.

  var chatCard = document.getElementById("card-chat");
  var chatLog = document.getElementById("chat-log");
  var chatInput = document.getElementById("chat-input");
  var chatSend = document.getElementById("chat-send");
  var chatOff = document.getElementById("chat-off");
  var chatClear = document.getElementById("chat-clear");
  var chatStarters = document.getElementById("chat-starters");
  var chatNameEl = document.getElementById("chat-name");
  var CHAT_KEEP = 40;
  var chatTurns = [];
  var chatReady = null;     // null until asked
  var chatBusy = false;
  var chatGreeted = false;

  var STARTERS = [
    t("Give me an idea for a picture"),
    t("What can I make here?"),
    // The odd one out on purpose: it shows them they can type in the other
    // language, so it swaps with the switch.
    t("Donne-moi une idée de dessin"),
  ];

  function chatRecall() {
    try {
      var raw = localStorage.getItem("makery:chat");
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.slice(-CHAT_KEEP) : [];
    } catch (e) { return []; }
  }

  function chatKeep() {
    try {
      localStorage.setItem("makery:chat", JSON.stringify(chatTurns.slice(-CHAT_KEEP)));
    } catch (e) { /* private browsing, or full */ }
  }

  function chatBubble(who, text, extra) {
    var row = document.createElement("div");
    row.className = "bubble " + who + (extra ? " " + extra : "");
    row.textContent = text;
    chatLog.appendChild(row);
    // Something it said is often an idea. Without these it was a nice answer
    // they then had to retype into the picture box by hand.
    if (who === "helper" && !extra && text && text.trim()) {
      chatLog.appendChild(chatUseRow(text.trim()));
    }
    return row;
  }

  function chatUseRow(text) {
    var row = document.createElement("div");
    row.className = "bubble-use";

    function button(label, onTap) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", function () { onTap(b); });
      row.appendChild(b);
      return b;
    }

    button(t("🎨 Make a picture of this"), function () { useFromChat("image", text); });
    button(t("🎬 Make a video of this"), function () { useFromChat("video", text); });
    button(t("📋 Copy"), function (b) {
      copyText(text).then(function (ok) {
        var was = b.textContent;
        b.textContent = ok ? t("✓ Copied") : t("✕ Couldn't copy");
        setTimeout(function () { b.textContent = was; }, 1600);
      });
    });
    return row;
  }

  // navigator.clipboard does not exist outside a secure context, which is
  // exactly where this runs on a plain-http LAN. The old execCommand still
  // works there, so it is the fallback rather than an error message.
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text)
        .then(function () { return true; })
        .catch(function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }

  function legacyCopy(text) {
    try {
      var box = document.createElement("textarea");
      box.value = text;
      box.setAttribute("readonly", "");
      box.style.position = "fixed";
      box.style.top = "-1000px";
      document.body.appendChild(box);
      box.select();
      var ok = document.execCommand("copy");
      box.remove();
      return ok;
    } catch (e) {
      return false;
    }
  }

  function useFromChat(which, text) {
    var card = cards[which];
    if (!card) return;
    showTab(which);
    card.textarea.value = text;
    if (card.syncClear) card.syncClear();
    if (card.rememberText) card.rememberText();
    if (card.helperMsg) {
      card.helperMsg.textContent =
        t("That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.",
          { name: chatNameEl.textContent || t("the helper") });
      card.helperMsg.hidden = false;
    }
    card.textarea.focus({ preventScroll: true });
    card.el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function paintChat() {
    chatLog.innerHTML = "";
    chatTurns.forEach(function (turn) { chatBubble(turn.who, turn.text); });
    chatLog.scrollTop = chatLog.scrollHeight;
    chatStarters.hidden = chatTurns.length > 1;
  }

  function chatSay(who, text) {
    chatTurns.push({ who: who, text: text });
    if (chatTurns.length > CHAT_KEEP) chatTurns = chatTurns.slice(-CHAT_KEEP);
    chatKeep();
  }

  function sendChat(text) {
    text = (text || chatInput.value).trim();
    if (!text || chatBusy || chatReady === false) return;
    chatBusy = true;
    chatInput.value = "";
    keep("chat-draft", "");
    chatStarters.hidden = true;

    // Sent before this turn is recorded, so the server sees the conversation as
    // it was - the message it is answering goes in its own field.
    var history = chatTurns.slice(-24);
    chatSay("kid", text);
    chatBubble("kid", text);
    var waiting = chatBubble("helper", "", "thinking");
    waiting.innerHTML = "<span></span><span></span><span></span>";
    chatLog.scrollTop = chatLog.scrollHeight;
    chatSend.disabled = true;

    postJSON("/api/chat", { message: text, history: history })
      .then(function (data) {
        waiting.remove();
        chatSay("helper", data.reply);
        chatBubble("helper", data.reply, data.blocked ? "blocked" : "");
      })
      .catch(function (err) {
        waiting.remove();
        // Not written into the conversation: it is about the machine, not
        // something the helper said, and it should not come back on reload.
        chatBubble("helper", err.message || GENERIC_ERROR, "oops");
      })
      .then(function () {
        chatBusy = false;
        chatSend.disabled = false;
        chatLog.scrollTop = chatLog.scrollHeight;
      });
  }

  function onChatShown() {
    if (chatReady === null) {
      chatReady = false;   // until told otherwise, so a double tap does nothing
      fetch("/api/chat")
        .then(readJSON)
        .then(function (data) {
          chatReady = !!data.ready;
          if (data.name) chatNameEl.textContent = data.name;
          if (!chatReady) {
            chatOff.textContent =
              t("The chat helper isn't set up on this machine yet. Everything else still works!");
            chatOff.hidden = false;
            chatInput.disabled = true;
            chatSend.disabled = true;
            return;
          }
          if (!chatTurns.length && !chatGreeted) {
            chatGreeted = true;
            chatSay("helper", data.greeting);
            paintChat();
          }
        })
        .catch(function () { chatReady = null; });   // ask again next time
    }
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  if (chatSend) {
    chatSend.addEventListener("click", function () { sendChat(); });
    chatInput.addEventListener("keydown", function (e) {
      // Enter sends; shift-enter is a new line. On the iPad the key says "send".
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
    remember(chatInput, "chat-draft");
    chatClear.addEventListener("click", function () {
      chatTurns = [];
      chatGreeted = false;
      chatKeep();
      paintChat();
      chatOff.hidden = true;
      onChatShown();
      showToast(t("Started a new chat. Your grown-ups can still see the old one."), { ms: 4000 });
    });
    STARTERS.forEach(function (line) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "starter";
      b.textContent = line;
      b.addEventListener("click", function () { sendChat(line); });
      chatStarters.appendChild(b);
    });
    chatTurns = chatRecall();
    paintChat();
  }

  // --- mix up an old one ----------------------------------------------------
  // One of their own past ideas with a brand new set of looks on it. Instant
  // once they have asked for anything before; the first few times it falls
  // through to the same inventor the Surprise me button uses.

  function remixIdea(card) {
    if (!card || activeCard) return;
    card.tweakSeed = null;
    var button = card.el.querySelector(".remix");
    var label = button ? button.textContent : "";
    if (button) { button.disabled = true; button.textContent = t("🎲 Shuffling..."); }
    var kind = card.kind === "video" ? currentMode() : card.kind;

    postJSON("/api/remix", { kind: kind })
      .then(function (data) {
        card.textarea.value = data.prompt || "";
        if (card.syncClear) card.syncClear();
        if (card.rememberText) card.rememberText();
        applyStyles(card, data.styles || {});
        if (card.helperMsg) {
          card.helperMsg.textContent = data.from_history
            ? t("One of your old ideas with a brand new look. Change anything you like!")
            : t("A brand new idea. Change anything you like!");
          card.helperMsg.hidden = false;
        }
      })
      .catch(function (err) { fail(card, err.message); })
      .then(function () {
        if (button) { button.disabled = false; button.textContent = label; }
      });
  }

  // --- make it again, but... ------------------------------------------------
  // The same words *and the same seed*, so a changed word gives a variation on
  // the picture they already have. "Make another like this" re-rolls; this does
  // not, and that difference is the whole point of having both.

  function tweakItem(item) {
    // A restyled picture's "but..." is the chips again, on the picture it was
    // made from, with the chip they tapped put back under their finger and
    // their own twist back in the box. What it reopens is the sheet, not a card.
    if (item.kind === "restyle") {
      if (!item.restyle_of) return;
      openRestyle({ id: item.restyle_of, version: item.version },
                  item.turned_into, item.twist || "", item.seed);
      return;
    }
    // An edit's "but..." is the change sheet again, on the picture it was made
    // from: the same seed with a changed instruction gives a variation on this
    // one. Their words are in `idea`, which for an edit is the instruction
    // itself rather than a description of a picture.
    if (isEdit(item)) {
      if (!item.edit_of) return;
      openChange({ id: item.edit_of, version: item.version },
                 item.idea || "", item.seed);
      return;
    }
    makeAnother(item);
    var card = item.media === "image" ? cards.image : cards.video;
    if (card.lastBody) card.lastBody = null;
    card.tweakSeed = item.seed;
    if (card.helperMsg) {
      card.helperMsg.textContent =
        t("Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.");
      card.helperMsg.hidden = false;
    }
    card.textarea.focus({ preventScroll: true });
  }

  // --- their colours ----------------------------------------------------------
  // Stored on the server, so their page looks the same on the tablet and on the
  // laptop - and mirrored into localStorage, which the snippet in <head> reads
  // before the first paint. Waiting for /api/app would flash the old colours
  // on every load.

  function applyTheme(name) {
    if (!name) return;
    document.documentElement.dataset.theme = name;
    try { localStorage.setItem("makery:theme", name); } catch (e) {}
  }

  function paintThemes(list, current) {
    var box = document.getElementById("theme-picks");
    if (!box || !list || !list.length) return;
    box.innerHTML = "";
    list.forEach(function (theme) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "theme-pick" + (theme.id === current ? " is-on" : "");
      button.dataset.theme = theme.id;
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", theme.id === current ? "true" : "false");
      var dots = document.createElement("span");
      dots.className = "theme-dots";
      dots.appendChild(document.createElement("span"));
      dots.appendChild(document.createElement("span"));
      dots.appendChild(document.createElement("span"));
      button.appendChild(dots);
      button.appendChild(document.createTextNode(theme.emoji + " " + theme.label));
      button.addEventListener("click", function () { chooseTheme(theme.id, box); });
      box.appendChild(button);
    });
  }

  function chooseTheme(name, box) {
    // Painted first and saved after: this is the one setting where the result
    // is the whole page, and a wait before it changes feels like a miss.
    applyTheme(name);
    Array.prototype.forEach.call(box.children, function (b) {
      var on = b.dataset.theme === name;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    });
    postJSON("/api/settings/theme", { theme: name })
      .catch(function () { showToast(t("Kept it on this device, but it wouldn't save.")); });
  }

  // --- which language they read ---------------------------------------------
  // Whoever is at the screen chooses, and it lives in a cookie: two sisters on
  // one iPad may well not read the same one, and the person holding it is the
  // one who knows. Not a profile setting, and nothing about it on the parent
  // page, which stays English.

  // Seven of them now, so the row wraps rather than sitting on one line - and
  // a flag is what they actually read at that size, the word under it being
  // half the width of the chip. The name of a language is always written in
  // that language: "Français" is what they are looking for, not "French".
  //
  // The flag is a compromise and worth being honest about: Spanish, German,
  // Portuguese and Dutch are spoken in more places than the flag on the chip,
  // and English is not only Britain's. They are here because a child picks a
  // picture out of seven far faster than a word, and the word is beside it.
  var LANGS = [
    { id: "en", flag: "🇬🇧", label: "English" },
    { id: "fr", flag: "🇫🇷", label: "Français" },
    { id: "de", flag: "🇩🇪", label: "Deutsch" },
    { id: "es", flag: "🇪🇸", label: "Español" },
    { id: "it", flag: "🇮🇹", label: "Italiano" },
    { id: "nl", flag: "🇳🇱", label: "Nederlands" },
    { id: "pt", flag: "🇵🇹", label: "Português" },
  ];

  function knownLang(id) {
    for (var i = 0; i < LANGS.length; i++) if (LANGS[i].id === id) return true;
    return false;
  }

  function paintLangs(current) {
    var box = document.getElementById("lang-picks");
    if (!box) return;
    // The server's answer wins over the cookie this page read, so a language
    // chosen on another device is what the row shows.
    var now = knownLang(current) ? current : I18N.lang;
    box.innerHTML = "";
    LANGS.forEach(function (lang) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "theme-pick lang-pick" + (lang.id === now ? " is-on" : "");
      button.dataset.lang = lang.id;
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", lang.id === now ? "true" : "false");
      button.textContent = lang.flag + " " + lang.label;
      button.addEventListener("click", function () { chooseLang(lang.id); });
      box.appendChild(button);
    });
  }

  function chooseLang(id) {
    if (id === I18N.lang) return;
    I18N.set(id);
    // Reloaded rather than repainted, the way picking a profile is: every
    // string on the page belongs to the language that was picked - the title,
    // the tabs, every dropdown, everything the server writes - and putting
    // them back one at a time is a long list of things to forget one of.
    window.location.reload();
  }

  // --- the strip across the top ---------------------------------------------

  // One <img> in the header and one in the Settings card, both on the same URL.
  // The server sends it no-store, but a browser that already has it painted
  // will not go and ask again on its own, so both get a fresh query string.
  function repaintBanner() {
    var bust = "banner.png?v=" + Date.now();
    Array.prototype.forEach.call(
      document.querySelectorAll('.banner img, #banner-preview'),
      function (img) { img.src = bust; });
  }

  function showBannerReset(custom) {
    var reset = document.querySelector(".banner-reset");
    if (reset) reset.hidden = !custom;
  }

  function useAsBanner(itemId, button) {
    var was = button ? button.textContent : "";
    if (button) { button.disabled = true; button.textContent = t("🖼️ Putting it up..."); }
    postJSON("/api/settings/banner", { item_id: itemId })
      .then(function () {
        repaintBanner();
        showBannerReset(true);
        closeGallery();
        showToast(t("That's the top of your page now! 🖼️"), { cheer: true });
      })
      .catch(function (err) { showToast(err.message || t("That one wouldn't go up there.")); })
      .then(function () {
        if (button) { button.disabled = false; button.textContent = was; }
      });
  }

  function resetBanner(button) {
    if (button) button.disabled = true;
    fetch("/api/settings/banner", { method: "DELETE" })
      .then(readJSON)
      .then(function () {
        repaintBanner();
        showBannerReset(false);
        showToast(t("Put back the one it came with."));
      })
      .catch(function () { showToast(t("Couldn't change it back.")); })
      .then(function () { if (button) button.disabled = false; });
  }

  // --- cutting a picture out ------------------------------------------------

  function makeSticker() {
    if (!viewing || viewing.media !== "image") return;
    var item = viewing;
    showToast(t("Cutting it out..."), { ms: 20000 });
    fetch("/api/gallery/" + encodeURIComponent(item.id) + "/sticker", { method: "POST" })
      .then(readJSON)
      .then(function (data) {
        refreshMine();
        showToast(t("It's a sticker! ✂️"), {
          cheer: true, ms: 6000,
          action: t("Show me"),
          onAction: function () { openViewerById(data.gallery_id); },
          bin: [data.gallery_id],
        });
      })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 8000 }); });
  }

  // --- renders they start from their gallery ----------------------------------
  // "Make it smooth", "Slow it down" and "Make it huge" are real renders: they
  // hold the card, they queue behind whatever else is running, and they take
  // long enough to need a progress bar. What they do not have is a maker card
  // to draw a result into - the new thing simply appears in the Gallery. So they
  // borrow the now-bar and the same Go locks every other job puts on, and
  // nothing else. The toast at the end is what takes them to it.

  var derivedCard = { kind: "derived" };
  var derivedJob = null;

  function watchDerived(jobId) {
    derivedJob = jobId;
    setBusy(derivedCard);
    setTimeout(function step() {
      if (derivedJob !== jobId) return;
      fetch("/api/job/" + jobId)
        .then(readJSON)
        .then(function (job) {
          if (derivedJob !== jobId) return;
          if (job.status === "done") {
            derivedJob = null;
            setIdle();
            finishNow(job);
            flashTitle(t("✅ Ready!"));
            ding();
            refreshMine();
            showToast(t(WHAT[job.kind] === "big picture" ? "It's ready! 🔍" : "It's ready! ✨"), {
              cheer: true, ms: 7000,
              action: t("Show me"),
              onAction: function () { if (job.filename) openViewerById(job.filename); },
              // This line is the whole of a derived render's result, so the
              // delete lives on it.
              bin: job.filename ? [job.filename] : null,
            });
            return;
          }
          if (job.status === "error" || job.status === "cancelled") {
            derivedJob = null;
            setIdle();
            hideNow();
            showToast(job.error || job.message || GENERIC_ERROR, { ms: 8000 });
            return;
          }
          showNow(derivedCard, job);
          setTimeout(step, POLL_MS);
        })
        // A blip on the wifi should not lose a render that is still going.
        .catch(function () { if (derivedJob === jobId) setTimeout(step, POLL_MS); });
    }, 300);
  }

  function startDerived(url, body, waitingLine) {
    armDing();
    showToast(waitingLine, { ms: 30000 });
    postJSON(url, body || {})
      .then(function (data) { watchDerived(data.job_id); })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 8000 }); });
  }

  function makeSmooth(slow) {
    if (!viewing || viewing.media !== "video") return;
    startDerived("/api/gallery/" + encodeURIComponent(viewing.id) + "/smooth",
      { slow: !!slow },
      slow ? t("Slowing it right down... it comes out quiet 🐌")
           : t("Smoothing it out... ✨"));
  }

  function makeHuge() {
    if (!viewing || viewing.media !== "image") return;
    startDerived("/api/gallery/" + encodeURIComponent(viewing.id) + "/huge", {},
      t("Making it huge... 🔍"));
  }

  // --- the three ways to change a picture they already have -------------------
  // These are not like "make it smooth": a model invents a whole picture from
  // their words, so they spend one of their pictures for the day and they go
  // through the same word filter every other prompt does. What they share with
  // the smooth/huge pair is where they start - the gallery viewer, with no
  // maker card - so they answer through watchDerived() too.

  var changeSheet = document.getElementById("change");
  var changeShot = document.getElementById("change-shot");
  var changeWords = document.getElementById("change-words");
  var changeIdeas = document.getElementById("change-ideas");
  var changeMeRow = document.getElementById("change-me-row");
  var changeMe = document.getElementById("change-me");
  var changeGo = document.getElementById("change-go");
  var changeStatus = document.getElementById("change-status");
  var changeFor = null;
  var changeSeed = null;

  // Written out rather than invented by a model: three examples is all they
  // needs to see what kind of sentence this box wants, and asking Ollama for
  // them would put a second model in front of a button that is already one
  // tap from a render.
  // Chips that fill the words box, so they are in their language: the server
  // translates what they send before it reaches the model, the same as
  // anything they type themselves.
  var CHANGE_IDEAS = [t("make it night-time"), t("make it snowy"),
                      t("add a rainbow"), t("make it look like a painting"),
                      t("put a hat on it"), t("make everything tiny")];

  CHANGE_IDEAS.forEach(function (idea) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "count-pick";
    b.textContent = idea;
    b.addEventListener("click", function () {
      changeWords.value = idea;
      changeWords.focus({ preventScroll: true });
    });
    changeIdeas.appendChild(b);
  });

  function openChange(item, words, seed) {
    changeFor = item;
    changeSeed = (seed === 0 || seed) ? seed : null;
    changeWords.value = words || "";
    changeStatus.hidden = true;
    changeGo.disabled = false;
    // Only once they have actually saved a face. Without one there is nothing to
    // put in the picture and the box would be a promise with nothing behind it.
    changeMeRow.hidden = !(me && me.avatar);
    changeMe.checked = false;
    changeShot.src = "/api/gallery/" + encodeURIComponent(item.id) + "/thumb?v=" + item.version;
    changeSheet.hidden = false;
    lockPage();
  }

  function closeChange() {
    changeSheet.hidden = true;
    changeShot.removeAttribute("src");
    changeFor = null;
    changeSeed = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function doChange() {
    if (!changeFor) return;
    if (!changeWords.value.trim()) {
      changeStatus.textContent = t("Tell me what should be different!");
      changeStatus.hidden = false;
      changeWords.focus({ preventScroll: true });
      return;
    }
    var id = changeFor.id;
    var body = { prompt: changeWords.value.trim(), with_me: !!changeMe.checked };
    if (changeSeed === 0 || changeSeed) body.seed = changeSeed;
    closeChange();
    closeGallery();
    startDerived("/api/gallery/" + encodeURIComponent(id) + "/edit", body,
                 t("Changing your picture... 🪄"));
  }

  // --- turn it into... ------------------------------------------------------
  // The one of these four that needs no sentence from them: a row of chips, one
  // instruction behind each, and the picture comes back drawn that way with
  // everything still where it was. Underneath it is the change sheet's shape
  // and the change sheet's route-shaped thing - one of their own pictures, one
  // of the day's pictures, and watchDerived() - so almost nothing here is new.

  var restyleSheet = document.getElementById("restyle");
  var restyleShot = document.getElementById("restyle-shot");
  var restyleWords = document.getElementById("restyle-words");
  var restyleChips = document.getElementById("restyle-chips");
  var restyleGo = document.getElementById("restyle-go");
  var restyleStatus = document.getElementById("restyle-status");
  var restyleFor = null;
  var restyleStyle = "";
  var restyleSeed = null;

  // Built from /api/styles, so the wording and the order of the row live on
  // the server beside the sentences they are short for - the same reason the
  // dropdowns are not in the HTML.
  function buildRestyleChips(list) {
    if (!restyleChips || !list || !list.length) return;
    restyleChips.textContent = "";
    list.forEach(function (style) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "count-pick";
      b.dataset.style = style.id;
      b.textContent = style.label;
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", "false");
      restyleChips.appendChild(b);
    });
    wireChoice(restyleChips.querySelectorAll(".count-pick"), function (btn) {
      restyleStyle = btn.dataset.style || "";
    });
    pickRestyle(restyleStyle);
  }

  // Lighting one in code rather than faking a click, for the reason `pickIn`
  // exists on the maker cards: the setters move the value and nothing else
  // puts the buttons right. An id the row does not have falls back to the
  // first chip - that is a page left open across a rebuild, not an error.
  function pickRestyle(id) {
    var chips = restyleChips ? restyleChips.querySelectorAll(".count-pick") : [];
    if (!chips.length) { restyleStyle = id || ""; return; }
    var wanted = null;
    Array.prototype.forEach.call(chips, function (b) {
      if (b.dataset.style === id) wanted = id;
    });
    if (!wanted) wanted = chips[0].dataset.style;
    Array.prototype.forEach.call(chips, function (b) {
      var on = b.dataset.style === wanted;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    });
    restyleStyle = wanted;
  }

  function openRestyle(item, style, words, seed) {
    restyleFor = item;
    restyleSeed = (seed === 0 || seed) ? seed : null;
    restyleWords.value = words || "";
    restyleStatus.hidden = true;
    restyleGo.disabled = false;
    pickRestyle(style || restyleStyle);
    restyleShot.src = "/api/gallery/" + encodeURIComponent(item.id) + "/thumb?v=" + item.version;
    restyleSheet.hidden = false;
    lockPage();
  }

  function closeRestyle() {
    restyleSheet.hidden = true;
    restyleShot.removeAttribute("src");
    restyleFor = null;
    restyleSeed = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function doRestyle() {
    if (!restyleFor) return;
    if (!restyleStyle) {
      // Only reachable if /api/styles never answered, which is the same blip
      // that empties the maker cards' dropdowns.
      restyleStatus.textContent = t("Pick what to turn it into!");
      restyleStatus.hidden = false;
      return;
    }
    var id = restyleFor.id;
    // Their words are optional, like the outpaint's and unlike the change
    // sheet's: the chip is a whole request by itself.
    var body = { style: restyleStyle, prompt: restyleWords.value.trim() };
    if (restyleSeed === 0 || restyleSeed) body.seed = restyleSeed;
    closeRestyle();
    closeGallery();
    startDerived("/api/gallery/" + encodeURIComponent(id) + "/restyle", body,
                 t("Drawing it again... 🎨"));
  }

  restyleGo.addEventListener("click", doRestyle);

  // --- what's outside the frame ---------------------------------------------

  var outsideSheet = document.getElementById("outside");
  var outsideShot = document.getElementById("outside-shot");
  var outsideWords = document.getElementById("outside-words");
  var outsideGo = document.getElementById("outside-go");
  var outsideStatus = document.getElementById("outside-status");
  var outsideFor = null;
  var outsideSide = "all";
  var outsideAmount = "bit";

  wireChoice(document.querySelectorAll("#outside-sides .count-pick"), function (btn) {
    outsideSide = btn.dataset.side || "all";
  });
  wireChoice(document.querySelectorAll("#outside-amounts .count-pick"), function (btn) {
    outsideAmount = btn.dataset.amount || "bit";
  });

  function openOutside(item) {
    outsideFor = item;
    outsideWords.value = "";
    outsideStatus.hidden = true;
    outsideGo.disabled = false;
    outsideShot.src = "/api/gallery/" + encodeURIComponent(item.id) + "/thumb?v=" + item.version;
    outsideSheet.hidden = false;
    lockPage();
  }

  function closeOutside() {
    outsideSheet.hidden = true;
    outsideShot.removeAttribute("src");
    outsideFor = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function doOutside() {
    if (!outsideFor) return;
    var id = outsideFor.id;
    // The words are optional here, unlike the change sheet: "show me more of
    // it" is a complete request on its own and the picture is the instruction.
    var body = { prompt: outsideWords.value.trim(), side: outsideSide,
                 amount: outsideAmount };
    closeOutside();
    closeGallery();
    startDerived("/api/gallery/" + encodeURIComponent(id) + "/outpaint", body,
                 t("Looking outside the frame... 🔭"));
  }

  // --- fix just this bit ----------------------------------------------------
  // The drawing pad they already know, in mask mode: one thick colour, a
  // see-through overlay so they can see what they are covering, and a words box
  // under the canvas. What the server gets is a separate black-and-white
  // canvas painted in step with the visible one - the overlay cannot be the
  // mask, because it has their picture underneath it.

  changeGo.addEventListener("click", doChange);
  outsideGo.addEventListener("click", doOutside);

  function fixThisBit(item) {
    openDraw(fileUrl(item), item);
  }

  function sendMask() {
    var item = maskFor;
    if (!item) return;
    var words = maskSay.value.trim();
    if (!words) {
      drawSheet.querySelector(".draw-note").textContent =
        t("Say what should be there instead, then tap Go.");
      maskSay.focus({ preventScroll: true });
      return;
    }
    if (!maskPainted) {
      drawSheet.querySelector(".draw-note").textContent =
        t("Paint over the bit you want changed first!");
      return;
    }
    var button = drawSheet.querySelector('[data-action="use-mask"]');
    button.disabled = true;
    maskCanvas.toBlob(function (blob) {
      var form = new FormData();
      form.append("mask", new File([blob], "mask.png", { type: "image/png" }));
      form.append("prompt", words);
      closeDraw();
      closeGallery();
      armDing();
      showToast(t("Fixing that bit... 🩹"), { ms: 30000 });
      fetch("/api/gallery/" + encodeURIComponent(item.id) + "/inpaint",
            { method: "POST", body: form })
        .then(readJSON)
        .then(function (data) { watchDerived(data.job_id); })
        .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 8000 }); })
        .then(function () { button.disabled = false; });
    }, "image/png");
  }

  // --- a sound effect on a video --------------------------------------------

  var soundSheet = document.getElementById("sounds");
  var soundVideo = document.getElementById("sound-video");
  var soundAt = document.getElementById("sound-at");
  var soundAtOut = document.getElementById("sound-at-out");
  var soundGrid = document.getElementById("sound-grid");
  var soundGo = document.getElementById("sound-go");
  var soundStatus = document.getElementById("sound-status");
  var soundFor = null;
  var soundPicked = "";
  var soundList = null;
  var soundPreview = null;

  function paintSounds() {
    soundGrid.innerHTML = "";
    (soundList || []).forEach(function (effect) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "sound-pick" + (soundPicked === effect.id ? " is-on" : "");
      b.innerHTML = "";
      var emoji = document.createElement("span");
      emoji.className = "sound-emoji";
      emoji.setAttribute("aria-hidden", "true");
      emoji.textContent = effect.emoji;
      b.appendChild(emoji);
      b.appendChild(document.createTextNode(effect.label));
      b.addEventListener("click", function () {
        soundPicked = effect.id;
        soundGo.disabled = false;
        paintSounds();
        // Hearing it is the whole reason to tap it.
        try {
          if (soundPreview) soundPreview.pause();
          soundPreview = new Audio("/api/sounds/" + encodeURIComponent(effect.id) + ".wav");
          soundPreview.play().catch(function () {});
        } catch (e) { /* no audio on this browser; the video still gets it */ }
      });
      soundGrid.appendChild(b);
    });
  }

  function showSoundAt() {
    soundAtOut.textContent = (+soundAt.value).toFixed(1) + "s";
  }

  function openSounds(item) {
    soundFor = item;
    soundPicked = "";
    soundGo.disabled = true;
    soundStatus.hidden = true;
    soundSheet.hidden = false;
    lockPage();
    soundVideo.src = fileUrl(item);
    soundAt.value = 0;
    showSoundAt();
    soundVideo.addEventListener("loadedmetadata", function once() {
      soundVideo.removeEventListener("loadedmetadata", once);
      soundAt.max = Math.max(0.5, (soundVideo.duration || 5) - 0.2).toFixed(1);
      soundAt.step = 0.1;
    });
    if (soundList) { paintSounds(); return; }
    fetch("/api/sounds").then(readJSON).then(function (data) {
      soundList = data.sounds || [];
      paintSounds();
    }).catch(function () { soundGrid.textContent = t("Couldn't load the sounds."); });
  }

  function closeSounds() {
    soundSheet.hidden = true;
    soundVideo.pause();
    soundVideo.removeAttribute("src");
    if (soundPreview) { soundPreview.pause(); soundPreview = null; }
    soundFor = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function applySound() {
    if (!soundFor || !soundPicked) return;
    var item = soundFor;
    soundGo.disabled = true;
    soundStatus.textContent = t("Putting it on...");
    soundStatus.hidden = false;
    postJSON("/api/gallery/" + encodeURIComponent(item.id) + "/sound",
             { effect: soundPicked, at: +soundAt.value })
      .then(function (data) {
        closeSounds();
        refreshMine();
        showToast(t("Sound added! 🔊"), {
          cheer: true, ms: 6000,
          action: t("Show me"),
          onAction: function () { openViewerById(data.gallery_id); },
          bin: [data.gallery_id],
        });
      })
      .catch(function (err) {
        soundStatus.textContent = err.message || GENERIC_ERROR;
        soundGo.disabled = false;
      });
  }

  // --- grabbing a picture out of a video ------------------------------------
  // The video scrubs instantly in the browser, but what they keep is decoded
  // on the server, and the two can land on different frames. So the picture
  // underneath is fetched from the server: what they see is what they get.

  var framerSheet = document.getElementById("framer");
  var frameVideo = document.getElementById("frame-video");
  var frameAt = document.getElementById("frame-at");
  var frameAtOut = document.getElementById("frame-at-out");
  var frameShot = document.getElementById("frame-shot");
  var frameGo = document.getElementById("frame-go");
  var frameStatus = document.getElementById("frame-status");
  var frameFor = null;
  var frameTimer = null;

  function refreshShot() {
    if (!frameFor) return;
    frameShot.src = "/api/gallery/" + encodeURIComponent(frameFor.id) +
      "/frame?at=" + (+frameAt.value).toFixed(2) + "&v=" + frameFor.version;
  }

  function scrubTo(seconds) {
    frameAtOut.textContent = (+seconds).toFixed(1) + "s";
    try { frameVideo.currentTime = +seconds; } catch (e) {}
    clearTimeout(frameTimer);
    frameTimer = setTimeout(refreshShot, 350);
  }

  function openFramer(item) {
    frameFor = item;
    frameStatus.hidden = true;
    frameGo.disabled = false;
    framerSheet.hidden = false;
    lockPage();
    frameVideo.src = fileUrl(item);
    frameAt.value = 0;
    frameShot.removeAttribute("src");
    frameVideo.addEventListener("loadedmetadata", function once() {
      frameVideo.removeEventListener("loadedmetadata", once);
      frameAt.max = Math.max(0.1, (frameVideo.duration || 5) - 0.05).toFixed(2);
      frameAt.step = 0.05;
      scrubTo(0);
    });
  }

  function closeFramer() {
    clearTimeout(frameTimer);
    framerSheet.hidden = true;
    frameVideo.pause();
    frameVideo.removeAttribute("src");
    frameShot.removeAttribute("src");
    frameFor = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function keepFrame() {
    if (!frameFor) return;
    var item = frameFor;
    frameGo.disabled = true;
    frameStatus.textContent = t("Keeping it...");
    frameStatus.hidden = false;
    postJSON("/api/gallery/" + encodeURIComponent(item.id) + "/frame", { at: +frameAt.value })
      .then(function (data) {
        closeFramer();
        refreshMine();
        showToast(t("Kept it as a picture! 📸"), {
          cheer: true, ms: 6000,
          action: t("Show me"),
          onAction: function () { openViewerById(data.gallery_id); },
          bin: [data.gallery_id],
        });
      })
      .catch(function (err) {
        frameStatus.textContent = err.message || GENERIC_ERROR;
        frameGo.disabled = false;
      });
  }

  // --- a sticker that moves -------------------------------------------------
  // The same scrubber as the frame grabber, with one extra question. The still
  // underneath is the *first* frame of the loop, fetched from the server for
  // the same reason the grabber does it: what they see is where it starts.
  // There is no moving preview, because making one is making the thing.

  var looperSheet = document.getElementById("looper");
  var loopVideo = document.getElementById("loop-video");
  var loopAt = document.getElementById("loop-at");
  var loopAtOut = document.getElementById("loop-at-out");
  var loopShot = document.getElementById("loop-shot");
  var loopGo = document.getElementById("loop-go");
  var loopStatus = document.getElementById("loop-status");
  var loopLengths = document.querySelectorAll("#loop-lengths .count-pick");
  var loopFor = null;
  var loopTimer = null;
  var loopSeconds = 2;

  function refreshLoopShot() {
    if (!loopFor) return;
    loopShot.src = "/api/gallery/" + encodeURIComponent(loopFor.id) +
      "/frame?at=" + (+loopAt.value).toFixed(2) + "&v=" + loopFor.version;
  }

  function loopScrubTo(seconds) {
    loopAtOut.textContent = (+seconds).toFixed(1) + "s";
    try { loopVideo.currentTime = +seconds; } catch (e) {}
    clearTimeout(loopTimer);
    loopTimer = setTimeout(refreshLoopShot, 350);
  }

  function openLooper(item) {
    loopFor = item;
    loopStatus.hidden = true;
    loopGo.disabled = false;
    looperSheet.hidden = false;
    lockPage();
    loopVideo.src = fileUrl(item);
    loopAt.value = 0;
    loopShot.removeAttribute("src");
    loopVideo.addEventListener("loadedmetadata", function once() {
      loopVideo.removeEventListener("loadedmetadata", once);
      // Always leave something to loop over, wherever they put the slider.
      loopAt.max = Math.max(0.1, (loopVideo.duration || 5) - 0.3).toFixed(2);
      loopAt.step = 0.05;
      loopScrubTo(0);
    });
  }

  function closeLooper() {
    clearTimeout(loopTimer);
    looperSheet.hidden = true;
    loopVideo.pause();
    loopVideo.removeAttribute("src");
    loopShot.removeAttribute("src");
    loopFor = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  function makeLoop() {
    if (!loopFor) return;
    var item = loopFor;
    loopGo.disabled = true;
    loopStatus.textContent = t("Making it...");
    loopStatus.hidden = false;
    postJSON("/api/gallery/" + encodeURIComponent(item.id) + "/loop",
             { at: +loopAt.value, seconds: loopSeconds })
      .then(function (data) {
        closeLooper();
        refreshMine();
        showToast(t("It moves! 🌀"), {
          cheer: true, ms: 6000,
          action: t("Show me"),
          onAction: function () { openViewerById(data.gallery_id); },
          bin: [data.gallery_id],
        });
      })
      .catch(function (err) {
        loopStatus.textContent = err.message || GENERIC_ERROR;
        loopGo.disabled = false;
      });
  }

  loopAt.addEventListener("input", function () { loopScrubTo(loopAt.value); });
  wireChoice(loopLengths, function (btn) {
    loopSeconds = parseFloat(btn.dataset.seconds) || 2;
  });
  loopGo.addEventListener("click", makeLoop);

  // --- which of these two? --------------------------------------------------

  var compareSheet = document.getElementById("compare");
  var compareA = document.getElementById("compare-a");
  var compareB = document.getElementById("compare-b");
  var compareBWrap = document.getElementById("compare-b-wrap");
  var compareHandle = document.getElementById("compare-handle");
  var compareSlider = document.getElementById("compare-slider");
  var compareStarA = document.getElementById("compare-star-a");
  var compareStarB = document.getElementById("compare-star-b");
  var comparing = [];

  // clip-path rather than a width: the second picture stays laid out at full
  // size and only the visible slice of it changes, so the two line up exactly.
  // Shrinking a wrapper instead squashes the image inside it.
  function wipeTo(percent) {
    compareBWrap.style.clipPath = "inset(0 " + (100 - percent) + "% 0 0)";
    compareHandle.style.left = percent + "%";
  }

  function starOne(which) {
    var item = comparing[which];
    if (!item) return;
    var button = which === 0 ? compareStarA : compareStarB;
    fetch("/api/gallery/" + encodeURIComponent(item.id) + "/favourite", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: true }),
    })
      .then(readJSON)
      .then(function () {
        item.favourite = true;
        button.textContent = t("⭐ Starred!");
        button.disabled = true;
        refreshMine();
      })
      .catch(function () {});
  }

  function openCompare(a, b) {
    comparing = [a, b];
    compareA.src = fileUrl(a);
    compareB.src = fileUrl(b);
    compareStarA.textContent = a.favourite ? t("⭐ Starred") : t("☆ This one’s best");
    compareStarB.textContent = b.favourite ? t("⭐ Starred") : t("☆ This one’s best");
    compareStarA.disabled = !!a.favourite;
    compareStarB.disabled = !!b.favourite;
    compareSlider.value = 50;
    wipeTo(50);
    compareSheet.hidden = false;
    lockPage();
  }

  function closeCompare() {
    compareSheet.hidden = true;
    compareA.removeAttribute("src");
    compareB.removeAttribute("src");
    comparing = [];
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  if (soundGo) soundGo.addEventListener("click", applySound);
  if (soundAt) soundAt.addEventListener("input", showSoundAt);
  if (frameGo) frameGo.addEventListener("click", keepFrame);
  if (frameAt) frameAt.addEventListener("input", function () { scrubTo(frameAt.value); });

  if (compareSlider) {
    compareSlider.addEventListener("input", function () { wipeTo(+compareSlider.value); });
    compareStarA.addEventListener("click", function () { starOne(0); });
    compareStarB.addEventListener("click", function () { starOne(1); });
  }

  // --- a character's own page -----------------------------------------------
  // Everything they are in, plus the three things looking after one means:
  // rename, reword the look, say goodbye. Reworded is the one that matters -
  // that sentence is repeated into every prompt they appear in, so it is the
  // difference between a character that works and one they delete and redo.

  function saveCharacter(id, changes) {
    fetch("/api/characters/" + encodeURIComponent(id), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    })
      .then(readJSON)
      .then(function () {
        return loadCast().then(function () {
          // loadCast repaints the shelf and the chips on every card; the page
          // they are standing on has to be told separately.
          if (castShowing === id) openCastSheet(id);
          showToast("Saved!", { ms: 2000 });
        });
      })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 5000 }); });
  }

  var castSheet = document.getElementById("castsheet");
  var castSheetName = document.getElementById("castsheet-name");
  var castSheetFace = document.getElementById("castsheet-face");
  var castSheetLook = document.getElementById("castsheet-look");
  var castSheetGrid = document.getElementById("castsheet-grid");
  var castSheetEmpty = document.getElementById("castsheet-empty");
  var castSheetForget = document.getElementById("castsheet-forget");
  var castSheetRename = document.getElementById("castsheet-rename");
  var castSheetRelook = document.getElementById("castsheet-relook");
  var castShowing = null;

  function openCastSheet(id) {
    if (!id) return;
    castShowing = id;
    castSheetGrid.innerHTML = "";
    castSheetEmpty.hidden = true;
    castSheet.hidden = false;
    lockPage();
    fetch("/api/characters/" + encodeURIComponent(id) + "/works")
      .then(readJSON)
      .then(function (data) {
        var who = data.character || {};
        castSheetName.textContent = who.name || t("Character");
        castSheetLook.textContent = who.look || "";
        if (who.picture_id) {
          castSheetFace.src = "/api/gallery/" + encodeURIComponent(who.picture_id) + "/thumb";
          castSheetFace.hidden = false;
        } else {
          castSheetFace.removeAttribute("src");
          castSheetFace.hidden = true;
        }
        var items = data.items || [];
        castSheetEmpty.hidden = items.length > 0;
        castSheetGrid.innerHTML = "";
        items.forEach(function (item) {
          var tile = document.createElement("button");
          tile.type = "button";
          tile.className = "tile";
          var img = document.createElement("img");
          img.loading = "lazy";
          img.alt = item.name || item.idea || "";
          img.src = "/api/gallery/" + encodeURIComponent(item.id) + "/thumb?v=" + item.version;
          tile.appendChild(img);
          tile.addEventListener("click", function () {
            closeCastSheet();
            openViewer(item, false);
          });
          castSheetGrid.appendChild(tile);
        });
      })
      .catch(function () {
        castSheetEmpty.textContent = t("Couldn't load them just now.");
        castSheetEmpty.hidden = false;
      });
  }

  function closeCastSheet() {
    disarm();
    castSheet.hidden = true;
    castShowing = null;
    if (sheet.hidden && viewer.hidden) unlockPage();
  }

  if (castSheetRename) {
    castSheetRename.addEventListener("click", function () {
      var who = whoIs(castShowing);
      if (!who) return;
      var name = window.prompt(t("What should they be called?"), who.name);
      if (name === null || !name.trim()) return;
      saveCharacter(who.id, { name: name.trim() });
    });
  }

  if (castSheetRelook) {
    castSheetRelook.addEventListener("click", function () {
      var who = whoIs(castShowing);
      if (!who) return;
      var look = window.prompt(
        t("One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes."),
        who.look || "");
      if (look === null || !look.trim()) return;
      saveCharacter(who.id, { look: look.trim() });
    });
  }

  if (castSheetForget) {
    castSheetForget.addEventListener("click", function (e) {
      if (!castShowing) return;
      if (!arm(castSheetForget, t("Really say goodbye?"))) return;
      var who = whoIs(castShowing);
      fetch("/api/characters/" + encodeURIComponent(castShowing), { method: "DELETE" })
        .then(readJSON)
        .then(function () {
          closeCastSheet();
          loadCast();
          showToast(t("Said goodbye to {name}. Their pictures are still in the Gallery.",
                      { name: (who && who.name) || "?" }), { ms: 5000 });
        })
        .catch(function () {});
    });
  }

  // Generation runs on the server, so a reload does not stop it. Reattach to
  // whatever is still going, or they would come back to a page that looks idle
  // while the GPU is busy - and every button would answer 409.
  // The parent page can close the factory and cap the day. Both arrive from
  // /api/allowance, checked on load and then every minute, so either takes
  // effect without a reload.
  // Back where they left off, unless a job is running - the reattach below
  // moves them to whichever card is working.
  var startTab = "image";
  try { startTab = localStorage.getItem("makery:tab") || "image"; } catch (e) {}
  showTab(startTab, { keepScroll: true });

  // [whose it is, what it is] - the name on the big line, the factory in gold
  // under it. The two languages put them in opposite order: English hangs the
  // name off the front ("Ada's AI Factory"), French puts it on the end
  // ("La fabrique IA d'Ada", eliding before a vowel), so which
  // half is which has to follow the language rather than be assumed.
  function titlePieces(title, parts) {
    // The server splits it, because it is the server that built the sentence
    // and it is the only one that knows the name. This used to be a regular
    // expression per language - " de " for French, " AI Factory" for English -
    // and seven of those is seven ways to print half a title.
    if (parts && parts.length === 2 && parts[0]) return parts;
    var at = title.indexOf(" AI Factory");
    return at > 0 ? [title.slice(0, at), "AI Factory"] : [title, ""];
  }

  fetch("/api/app").then(readJSON).then(function (data) {
    appTitle = data.title || appTitle;
    appKid = data.kid || "";
    document.title = appTitle;
    var h1 = document.getElementById("app-title");
    if (h1) {
      // The h1 is a flex column, so each piece is a line: the name big and
      // white, the factory in gold underneath.
      var pieces = titlePieces(appTitle, data.title_parts);
      h1.textContent = pieces[0];
      if (pieces[1]) {
        var span = document.createElement("span");
        span.textContent = pieces[1];
        h1.appendChild(span);
      }
    }
    // "Put the first one back" only means something once they have changed it.
    showBannerReset(!!data.banner_custom);
    // The server is the one that knows; a device that had never been used
    // before still gets their colours.
    applyTheme(data.theme);
    paintThemes(data.themes, data.theme);
    paintLangs(data.lang);
  }).catch(function () {});

  checkQuiz();
  loadCast();
  loadHistory();
  refreshAllowance();
  setInterval(refreshAllowance, 60000);

  fetch("/api/active")
    .then(readJSON)
    .then(function (data) {
      var job = data.job;
      if (!job) return;
      // One they started from their gallery. It has no card to reattach to - the
      // now-bar and the Go locks are the whole of its user interface.
      if (TAB_FOR_KIND[job.kind] === "mine") {
        showNow(derivedCard, job);
        watchDerived(job.id);
        return;
      }
      // A job the story card started comes back to the story card, whatever
      // kind it is: the picture, the film and the song all run through routes
      // the other cards own, and only the card that started one knows it did.
      if (cards.story && storyOwns(job.id)) {
        showTab("story");
        setBusy(cards.story);
        showNow(cards.story, job);
        cards.story.jobId = job.id;
        cards.story.status.hidden = false;
        setProgress(cards.story, job.progress);
        showStatus(cards.story, job.message, false);
        showTiming(cards.story, job);
        poll(cards.story, job.id);
        return;
      }
      var card = cards[job.kind === "comic" ? "comic"
        : job.kind === "image" ? "image" : "video"];
      if (job.kind === "i2v") setMode("i2v");
      else if (job.kind === "t2v") setMode("t2v");
      else if (job.kind === "story") setMode("story");
      else if (job.kind === "flf") setMode("flf");

      showTab(TAB_FOR_KIND[job.kind] || "image");
      setBusy(card);
      showNow(card, job);
      card.jobId = job.id;
      card.status.hidden = false;
      setProgress(card, job.progress);
      showStatus(card, job.message, false);
      showTiming(card, job);
      // They reloaded half way through four at once: the ones already drawn
      // are theirs and come straight back, rather than the page pretending the
      // job has made nothing yet.
      if (job.kind === "image" && job.wanted > 1 &&
          job.filenames && job.filenames.length) {
        growChoices(card, job);
      }
      poll(card, job.id);
    })
    .catch(function () { /* nothing running, or the backend is down */ });



  // --- the story maker --------------------------------------------------------
  //
  // The sixth card, and the only one that renders nothing of its own. Every
  // step is one of the other cards' routes - `/api/generate/image`,
  // `/api/generate/story`, `/api/song-words` + `/api/generate/music`, and one
  // new one that lays the song under the film - run in order, with what each
  // made on the screen before the next one starts.
  //
  // That order is the whole feature. Filming three parts off a picture they have
  // not seen is three minutes of GPU spent on a guess; showing them the opening
  // frame first costs twelve seconds and makes the rest theirs.
  //
  // It has **no allowance of its own**. The picture step spends a picture, the
  // film step spends one video per part, the song step spends a song, each
  // through the same `_require_budget` its own card uses. Putting it together
  // spends nothing at all: no GPU, no model, just a remux.

  var STORY_STEPS = ["idea", "picture", "film", "song", "together"];

  // What the card remembers between reloads. The ids matter more than the
  // step does: a Stop half way through the film, or a reload, must not lose
  // the picture they chose or the song they have already heard.
  var story = { step: "idea", ids: {}, jobId: null, done: null };

  function storySave() {
    keep("story", JSON.stringify({ step: story.step, ids: story.ids,
                                   jobId: story.jobId, done: story.done }));
  }

  function storyLoad() {
    var raw = recall("story");
    if (!raw) return;
    try {
      var saved = JSON.parse(raw);
      if (saved && STORY_STEPS.indexOf(saved.step) >= 0) {
        story.step = saved.step;
        story.ids = saved.ids || {};
        story.jobId = saved.jobId || null;
        story.done = saved.done || null;
      }
    } catch (e) {}
  }

  // Whether a running job is one of ours. `/api/active` says what is being
  // made and by which route, and three of the four routes belong to other
  // cards, so the id is the only thing that can answer this.
  function storyOwns(jobId) { return !!jobId && story.jobId === jobId; }

  function storyAt(step) { return STORY_STEPS.indexOf(step); }

  // Which steps this installation can actually do. Not a rule about them - a
  // parent has switched a maker off, or the machine has no ACE-Step model.
  function storyCan(step) {
    if (step === "picture") return storySteps.picture;
    if (step === "film") return storySteps.video;
    if (step === "song") return storySteps.music;
    // Putting it together needs something to put together.
    if (step === "together") return !!(story.ids.film && story.ids.song);
    return true;
  }

  function sayWhatIsOff() {
    var line = document.getElementById("story-off");
    if (!line) return;
    var missing = [];
    if (!storySteps.picture) missing.push(t("the opening picture"));
    if (!storySteps.music) missing.push(t("the song"));
    line.hidden = missing.length === 0;
    if (missing.length) {
      line.textContent = missing.length === 1
        ? t("One bit is switched off right now: {what}. The rest still works!",
            { what: missing[0] })
        : t("Two bits are switched off right now: {what} and {other}. The rest still works!",
            { what: missing[0], other: missing[1] });
    }
  }

  // What the card looks like at each step: which settings are on show, what
  // the big button says, and the line above the words box that says what this
  // step is for.
  var STORY_FACE = {
    idea: { go: "That's my story!", say: "First, what happens? A beginning, a middle and an end." },
    picture: { go: "🎨 Draw the opening picture", say: "Now the very first thing we see. You can keep trying until you like it." },
    film: { go: "🎬 Film it!", say: "Each part carries on from the last frame of the one before." },
    song: { go: "🎵 Write a song for it", say: "Words about your story, as long as your film." },
    together: { go: "✨ Put it all together", say: "Your song, under your film. This is the last bit!" }
  };

  function storyPaint(card) {
    var step = story.step;
    var at = storyAt(step);
    var face = STORY_FACE[step] || STORY_FACE.idea;

    Array.prototype.forEach.call(card.el.querySelectorAll(".trail"), function (chip) {
      var mine = storyAt(chip.dataset.step);
      chip.classList.toggle("is-on", chip.dataset.step === step);
      chip.classList.toggle("done", mine < at);
      chip.disabled = mine > at;
    });

    var says = document.getElementById("story-say");
    if (says) says.textContent = t(face.say);
    card.button.textContent = t(face.go);

    // The words box is only editable while the idea is the question; after
    // that it is what the rest of the story is being made from, and changing
    // it half way would quietly disagree with the picture already on screen.
    var idea = card.el.querySelector(".idea");
    if (idea) idea.hidden = step !== "idea";

    show(card, ".setting.shape", step === "picture" || (step === "film" && !story.ids.picture));
    show(card, ".setting.parts", step === "film");
    show(card, ".setting.howlong", step === "film");
    show(card, ".setting.keep-sound", step === "together");
    show(card, ".setting.extras", step === "picture");
    var box = card.el.querySelector(".settings");
    if (box) box.hidden = !card.el.querySelector(".setting:not([hidden])");

    // Skipping is for the two steps that are genuinely optional. The film is
    // not one of them, and neither is the idea.
    card.skip.hidden = !(step === "picture" || step === "song");
    // "Next" appears once this step has something to show for itself.
    card.next.hidden = !storyMade(step);
    card.button.hidden = !storyCan(step);
    // What this step costs, and how long it takes, both follow the step.
    renderAllowance();
    refreshEta(card);
    storySave();
  }

  function show(card, selector, on) {
    var el = card.el.querySelector(selector);
    if (el) el.hidden = !on;
  }

  function storyMade(step) {
    if (step === "picture") return !!story.ids.picture;
    if (step === "film") return !!story.ids.film;
    if (step === "song") return !!story.ids.song;
    if (step === "together") return !!story.done;
    return false;
  }

  function storyMove(card, step) {
    story.step = step;
    clearResult(card);
    card.status.hidden = true;
    storyPaint(card);
    // Whatever this step made last time comes straight back, so stepping
    // backwards is looking at it again rather than starting it again.
    if (storyMade(step)) storyShowSaved(card, step);
    card.el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function storyNext(card) {
    var at = storyAt(story.step);
    for (var i = at + 1; i < STORY_STEPS.length; i++) {
      if (storyCan(STORY_STEPS[i]) || STORY_STEPS[i] === "together") {
        storyMove(card, STORY_STEPS[i]);
        return;
      }
    }
    storyMove(card, "together");
  }

  // --- what each step actually sends ------------------------------------------

  function storyGo(card) {
    var idea = card.textarea.value.trim();
    if (!idea) {
      fail(card, t("Type something you'd like to make first!"));
      return;
    }
    if (story.step === "idea") { story.ids = {}; story.done = null; storyNext(card); return; }
    if (story.step === "picture") return storyPicture(card, idea);
    if (story.step === "film") return storyFilm(card, idea);
    if (story.step === "song") return storySong(card, idea);
    if (story.step === "together") return storyTogether(card);
  }

  function storyStart(card, what, words) {
    startJob(card, what, words);
    // `startJob` learns the id from the route's own answer, which is a round
    // trip away, so it is not there yet. That id is the only thing a reload
    // can use to know the running job belongs to *this* card - three of the
    // four routes are other cards' - so it is written down the moment it
    // exists rather than when the step finishes. Caught by reloading twenty
    // seconds into a film, which came back on the Video tab.
    var tries = 0;
    (function grab() {
      if (card.jobId) { story.jobId = card.jobId; storySave(); return; }
      if (tries++ < 150) setTimeout(grab, 100);
    })();
  }

  function storyPicture(card, idea) {
    var body = { prompt: idea, orientation: card.orientation };
    var picked = chosenStyles(card);
    if (Object.keys(picked).length) body.styles = picked;
    card.lastBody = { kind: "image", body: body };
    storyStart(card, card.lastBody, t("Thinking up your picture..."));
  }

  function storyFilm(card, idea) {
    var body = {
      prompt: idea, parts: card.parts, orientation: card.orientation,
      duration: card.seconds, quality: "normal"
    };
    if (story.ids.picture) body.source_gallery_id = story.ids.picture;
    // The film opens on a card with their story's name on it, drawn here on a
    // canvas the way the movie maker's is - the server has no fonts and needs
    // none. It is 2 seconds long, which `gallery.join` decides.
    var wh = SHAPES[card.orientation] || SHAPES.landscape;
    var canvas = document.createElement("canvas");
    drawTitleCard(canvas, idea.slice(0, 60), wh[0], wh[1]);
    try { body.title_card = canvas.toDataURL("image/png"); } catch (e) {}
    card.lastBody = { kind: "story", body: body };
    storyStart(card, card.lastBody, t("Working out your story..."));
  }

  function storySong(card, idea) {
    // As long as the film, within whatever the parent has set the song slider
    // to. A song that stops half way through the last scene is worse than one
    // that runs to the end and gets trimmed by a second.
    var want = storyFilmSeconds(card);
    var low = LENGTHS.music[0], high = LENGTHS.music[2];
    var seconds = Math.max(low, Math.min(high, Math.round(want)));

    setBusy(card);
    clearResult(card);
    card.status.hidden = false;
    card.timing.hidden = true;
    setProgress(card, 0);
    showStatus(card, t("Writing the words..."), false);
    postJSON("/api/song-words", { prompt: idea, styles: {} })
      .then(function (words) {
        var body = {
          prompt: words.tags || idea,
          lyrics: words.lyrics || "",
          singing: !!words.lyrics,
          seconds: seconds
        };
        card.lastBody = { kind: "music", body: body };
        setIdle();
        storyStart(card, card.lastBody, t("Working out the tune..."));
      })
      .catch(function (err) {
        setIdle();
        fail(card, err.message);
      });
  }

  // How long the film came out. The joined file knows exactly, and the gallery
  // listing carries it; before that answer is in, the arithmetic the job was
  // asked for is close enough to ask for a song with.
  function storyFilmSeconds(card) {
    for (var i = 0; i < allItems.length; i++) {
      if (allItems[i].id === story.ids.film && allItems[i].duration) {
        return allItems[i].duration;
      }
    }
    return card.seconds * (card.parts || 2) + 2;
  }

  function storyTogether(card) {
    if (!story.ids.film || !story.ids.song) {
      fail(card, t("Make the film and the song first!"));
      return;
    }
    var keepSound = document.getElementById("story-keep-sound");
    setBusy(card);
    clearResult(card);
    card.status.hidden = false;
    card.timing.hidden = true;
    setProgress(card, 0.4);
    showStatus(card, t("Putting your story together..."), false);
    postJSON("/api/story/finish", {
      film: story.ids.film,
      song: story.ids.song,
      picture: story.ids.picture || "",
      keep_sound: !keepSound || keepSound.checked
    })
      .then(function (data) {
        story.done = data.gallery_id;
        setProgress(card, 1);
        showStatus(card, t("Your story is ready!"), false);
        setIdle();
        storyPaint(card);
        storyShowSaved(card, "together");
        ding();
        flashTitle(t("✅ Ready!"));
        refreshMine();
      })
      .catch(function (err) {
        setIdle();
        fail(card, err.message);
      });
  }

  // --- what came back ---------------------------------------------------------

  function storyLanded(card, job) {
    refreshEta(card);
    story.jobId = null;
    if (job.kind === "image" && job.filename) story.ids.picture = job.filename;
    if (job.kind === "story") story.ids.film = (job.extra && job.extra.movie) || null;
    if (job.kind === "music" && job.filename) story.ids.song = job.filename;
    storyPaint(card);
    storyShowSaved(card, story.step);
  }

  function storyShowSaved(card, step) {
    var id = step === "picture" ? story.ids.picture
      : step === "film" ? story.ids.film
        : step === "song" ? story.ids.song
          : story.done;
    if (!id) { card.result.hidden = true; return; }
    card.result.innerHTML = "";
    var stamp = encodeURIComponent(String(Date.now()));
    var src = "/api/gallery/" + encodeURIComponent(id) + "/file?v=" + stamp;
    var poster = "/api/gallery/" + encodeURIComponent(id) + "/poster?v=" + stamp;

    var media;
    if (step === "song") {
      media = songPlayer({ filename: id, id: stamp }, src);
    } else if (step === "picture") {
      media = document.createElement("img");
      media.src = src;
      media.alt = t("The picture you made");
    } else {
      media = document.createElement("video");
      media.src = src;
      media.controls = true;
      media.playsInline = true;
      media.preload = "metadata";
      media.poster = poster;
    }
    card.result.appendChild(media);

    var actions = document.createElement("div");
    actions.className = "actions";

    if (step !== "together") {
      var again = document.createElement("button");
      again.type = "button";
      again.className = "again";
      again.textContent = t("🔁 Make another");
      again.disabled = !!activeCard;
      again.addEventListener("click", function () { storyGo(card); });
      actions.appendChild(again);
    } else {
      var save = document.createElement("a");
      save.href = "/api/gallery/" + encodeURIComponent(id) + "/file?v=" + stamp + "&download=1";
      save.setAttribute("download", id);
      save.textContent = t("⬇︎ Save my story");
      actions.appendChild(save);

      var fresh = document.createElement("button");
      fresh.type = "button";
      fresh.className = "again";
      fresh.textContent = t("🎭 Start a new story");
      fresh.disabled = !!activeCard;
      fresh.addEventListener("click", function () { resetCard(card); });
      actions.appendChild(fresh);
    }

    // The bin takes away *this* step's thing and nothing else: the picture a
    // film was made from is a picture of theirs, and binning four things when
    // they asked to bin one is not what a bin button promises.
    actions.appendChild(binButton(card, [id], function () {
      if (step === "picture") story.ids.picture = null;
      else if (step === "film") story.ids.film = null;
      else if (step === "song") story.ids.song = null;
      else story.done = null;
      storyPaint(card);
      card.result.hidden = true;
      offerUndo([id], function () {
        if (step === "picture") story.ids.picture = id;
        else if (step === "film") story.ids.film = id;
        else if (step === "song") story.ids.song = id;
        else story.done = id;
        storyPaint(card);
        storyShowSaved(card, step);
      });
    }));

    card.result.appendChild(actions);
    card.result.hidden = false;
    refreshMine();
  }

  // --- wiring -----------------------------------------------------------------

  function storyReset(card) {
    story.step = "idea";
    story.ids = {};
    story.jobId = null;
    story.done = null;
    clearResult(card);
    card.status.hidden = true;
    card.parts = 2;
    pickIn(card.partPicks, "parts", 2);
    var keepSound = document.getElementById("story-keep-sound");
    if (keepSound) keepSound.checked = true;
    storyPaint(card);
  }

  if (cards.story) {
    (function wireStory() {
      var card = cards.story;
      card.skip = card.el.querySelector(".story-skip");
      card.next = card.el.querySelector(".story-next");
      card.parts = 2;
      card.skip.addEventListener("click", function () { storyNext(card); });
      card.next.addEventListener("click", function () { storyNext(card); });
      card.el.addEventListener("click", function (event) {
        var chip = event.target.closest(".trail");
        if (!chip || chip.disabled || activeCard) return;
        storyMove(card, chip.dataset.step);
      });
      storyLoad();
      sayWhatIsOff();
      storyPaint(card);
      if (storyMade(story.step)) storyShowSaved(card, story.step);
    })();
  }

  // --- who is using it -------------------------------------------------------
  // A household with one child sees none of this: /api/profiles says pick:false
  // and the chip, the picker and the "You" row all stay hidden. The cost of a
  // feature to somebody who does not want it should be nothing.

  var me = null;
  // Everybody, for putting a face and a name on a family-shelf tile that is
  // not theirs, and `severalWho` for whether the family shelf and its button
  // exist at all. With one profile both stay as they start and the page is
  // exactly the page it was before any of this.
  var whoAll = [];
  var severalWho = false;
  var faceChoices = { emoji: [], colours: [] };
  var whoBox = document.getElementById("whoami");
  var facesBox = document.getElementById("faces");
  var meChip = document.getElementById("me-chip");
  var meRow = document.getElementById("me-row");

  // Paint somebody's face into a round or square hole: the picture if they
  // have made one, their emoji on their colour if they have not. A colour and
  // an emoji is a perfectly good face - it means a profile works the moment it
  // is named, with the picture as the treat rather than the toll.
  function faceInto(el, who) {
    if (!el || !who) return;
    el.style.setProperty("--face", who.colour || "#f7b32b");
    el.textContent = "";
    if (who.avatar) {
      var img = document.createElement("img");
      img.src = "/api/profiles/" + encodeURIComponent(who.id) + "/avatar?v=" + faceVersion;
      img.alt = "";
      el.appendChild(img);
    } else {
      el.textContent = who.emoji || "🦊";
    }
  }
  var faceVersion = Date.now();

  function pickedAlready() {
    try { return !!sessionStorage.getItem("makery:picked"); } catch (e) { return false; }
  }

  function loadWho() {
    return fetch("/api/profiles").then(readJSON).then(function (data) {
      var everyone = data.who || [];
      whoAll = everyone;
      severalWho = !!data.pick;
      faceChoices = { emoji: data.emoji || [], colours: data.colours || [] };
      me = everyone.filter(function (w) { return w.is_me; })[0] || everyone[0] || null;

      // The Gallery page is painted from its own fetch, and the two race.
      // Repaint from what is already in hand rather than asking the server a
      // second time - the Family shelf and the maker faces both needed this
      // answer and may have been painted without it.
      if (allItems.length) paintMine();
      if (!sheet.hidden) paintShelves();

      if (meChip) meChip.hidden = !data.pick;
      // The "You" row goes with the chip. With one person there is nowhere a
      // face would be shown, so it would be a control over something invisible
      // - and the first thing it offers is a render.
      if (meRow) meRow.hidden = !data.pick || !me;
      if (me) {
        faceInto(document.getElementById("me-chip-face"), me);
        document.getElementById("me-chip-name").textContent = me.name;
        faceInto(document.getElementById("me-big"), me);
        document.getElementById("me-who").textContent = t("You're {name}!", { name: me.name });
        document.getElementById("me-clear").hidden = !me.avatar;
      }
      paintFaces(everyone);
      paintEmojiPicks();
      // Once a visit, not once a reload. Picking reloads the page - the title,
      // the colours, the gallery and the tabs all belong to whoever was picked
      // - and without this that reload would land straight back on the picker.
      if (data.pick && !pickedAlready()) showPicker();
    }).catch(function () { /* the page still works without a picker */ });
  }

  function paintFaces(everyone) {
    if (!facesBox) return;
    facesBox.textContent = "";
    (everyone || []).forEach(function (who) {
      var tile = document.createElement("button");
      tile.type = "button";
      tile.className = "face" + (who.is_me ? " is-on is-me" : "");
      var pic = document.createElement("span");
      pic.className = "face-pic";
      faceInto(pic, who);
      var name = document.createElement("span");
      name.className = "face-name";
      name.textContent = who.name;
      tile.appendChild(pic);
      tile.appendChild(name);
      tile.addEventListener("click", function () { becomeWho(who); });
      facesBox.appendChild(tile);
    });
    var note = document.getElementById("whoami-note");
    if (note) note.textContent = (everyone || []).length
      ? t("Tap your face. A grown-up adds and changes these on the parent page.")
      : "";
  }

  function showPicker() {
    if (!whoBox) return;
    whoBox.hidden = false;
    lockPage();
  }

  function becomeWho(who) {
    try { sessionStorage.setItem("makery:picked", who.id); } catch (e) {}
    if (me && who.id === me.id) {
      whoBox.hidden = true;
      unlockPage();
      return;
    }
    // A full reload rather than repainting. Everything on this page belongs to
    // whoever is signed in - the title, the colours, the tabs that exist, the
    // gallery, the countdown, the sums - and putting them all back one at a
    // time is a long list of things to forget one of.
    postJSON("/api/profiles/pick", { id: who.id })
      .then(function () { location.reload(); })
      .catch(function (err) { showToast(err.message || GENERIC_ERROR, { ms: 6000 }); });
  }

  function paintEmojiPicks() {
    var box = document.getElementById("me-emoji-picks");
    if (!box || !me) return;
    box.textContent = "";
    faceChoices.emoji.forEach(function (glyph) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = glyph;
      b.className = glyph === me.emoji && !me.avatar ? "is-on" : "";
      b.addEventListener("click", function () {
        fetch("/api/profiles/" + encodeURIComponent(me.id), {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ emoji: glyph }),
        }).then(readJSON).then(function () {
          // Choosing a face means using it, so a picture they have made steps
          // aside - otherwise the tap appears to do nothing at all.
          return fetch("/api/profiles/" + encodeURIComponent(me.id) + "/avatar",
                       { method: "DELETE" });
        }).then(function () { faceVersion = Date.now(); return loadWho(); })
          .catch(function () { showToast(GENERIC_ERROR, { ms: 6000 }); });
      });
      box.appendChild(b);
    });
  }

  function useAsFace(itemId, button) {
    if (!me) return;
    if (button) { button.disabled = true; button.textContent = t("👤 Making it you..."); }
    postJSON("/api/profiles/" + encodeURIComponent(me.id) + "/avatar",
             { gallery_id: itemId })
      .then(function () {
        faceVersion = Date.now();
        loadWho();
        showToast(t("That's you now! 👤"), { cheer: true, ms: 6000 });
        if (button) { button.disabled = false; button.textContent = t("👤 That one's me"); }
      })
      .catch(function (err) {
        if (button) { button.disabled = false; button.textContent = t("👤 That one's me"); }
        showToast(err.message || GENERIC_ERROR, { ms: 8000 });
      });
  }

  // --- three questions, and then the Picture card does the work --------------
  // Not its own maker. A picture of you is a picture: same route, same word
  // filter, same daily allowance, same four-at-once. This fills the card in
  // and takes them there, which is the handoff "Animate this" already uses.

  var WIZ_WHAT = ["a fox", "a cat", "a dog", "a dragon", "a robot", "an owl",
                  "a unicorn", "a penguin", "an astronaut", "a wizard",
                  "a superhero", "a pirate", "a mermaid", "a knight",
                  "a panda", "an octopus"];
  var WIZ_COLOUR = ["purple", "blue", "green", "orange", "pink", "red",
                    "yellow", "rainbow", "silver", "golden"];
  var WIZ_EXTRA = ["a wizard hat", "big round glasses", "a stripy scarf",
                   "a cape", "headphones", "a flower crown", "a bow tie",
                   "freckles"];

  var wiz = { what: "", colour: "", extras: [] };
  var wizSheet = document.getElementById("mewiz");

  function wizPicks(box, list, multi, onPick) {
    box.textContent = "";
    list.forEach(function (word) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = t(word);
      b.dataset.word = word;
      b.addEventListener("click", function () {
        if (multi) {
          b.classList.toggle("is-on");
        } else {
          Array.prototype.forEach.call(box.children, function (c) {
            c.classList.toggle("is-on", c === b);
          });
        }
        onPick(word, b.classList.contains("is-on"));
        wizPreview();
      });
      box.appendChild(b);
    });
  }

  function wizWords() {
    var own = (document.getElementById("mewiz-own").value || "").trim();
    var more = (document.getElementById("mewiz-more").value || "").trim();
    var subject = own || (wiz.what ? t(wiz.what) : "");
    if (!subject) return "";
    var wearing = wiz.extras.map(function (w) { return t(w); });
    if (more) wearing.push(more);
    // One sentence per language, not one built from fragments: English puts
    // the colour in front of the noun with the article in front of that
    // ("a friendly purple fox"), French puts it after and keeps the article on
    // the choice, where the gender travels with it ("un renard en violet").
    var out = t("wiz-sentence", {
      thing: subject,
      // "a friendly" already carries the article in English, so the one on the
      // pick goes: it used to read "a friendly a fox".
      bare: subject.replace(/^(a|an|the)\s+/i, "").trim(),
      colour: wiz.colour ? t("wiz-colour", { colour: t(wiz.colour) }) : "",
      wearing: wearing.length
        ? t("wiz-wearing", { list: wearing.join(t("wiz-and")) }) : "",
    });
    return out.replace(/\s+/g, " ").replace(/ ,/g, ",").trim();
  }

  function wizPreview() {
    var words = wizWords();
    var box = document.getElementById("mewiz-preview");
    box.textContent = words || t("Pick what you are to get started!");
  }

  function openWizard() {
    if (!wizSheet) return;
    // Fresh every time. The buttons are rebuilt below with nothing pressed,
    // and a preview built from last time's picks under unpressed buttons is
    // a lie that Go would then act on.
    wiz = { what: "", colour: "", extras: [] };
    document.getElementById("mewiz-own").value = "";
    document.getElementById("mewiz-more").value = "";
    wizPicks(document.getElementById("mewiz-what"), WIZ_WHAT, false,
             function (word) { wiz.what = word; });
    wizPicks(document.getElementById("mewiz-colour"), WIZ_COLOUR, false,
             function (word) { wiz.colour = word; });
    wizPicks(document.getElementById("mewiz-extra"), WIZ_EXTRA, true,
             function (word, on) {
               wiz.extras = wiz.extras.filter(function (w) { return w !== word; });
               if (on) wiz.extras.push(word);
             });
    document.getElementById("mewiz-own").oninput = wizPreview;
    document.getElementById("mewiz-more").oninput = wizPreview;
    wizPreview();
    wizSheet.hidden = false;
    lockPage();
  }

  function closeWizard() {
    if (!wizSheet) return;
    wizSheet.hidden = true;
    unlockPage();
  }

  function wizardGo() {
    var words = wizWords();
    if (!words) {
      showToast(t("Pick what you are first!"), { ms: 5000 });
      return;
    }
    var card = cards.image;
    if (!card) {
      showToast(t("Making pictures is switched off right now."), { ms: 6000 });
      return;
    }
    closeWizard();
    card.textarea.value = words;
    keep("text:image", words);
    if (card.syncClear) card.syncClear();
    // Square, four at once, and drawn as a character - which is the mode that
    // puts the subject alone on a plain background. That is what makes a face
    // read as a face at 30 pixels in the corner of the banner.
    setOrientation(card, "square");
    card.count = 4;
    pickIn(card.counts, "count", 4);
    if (card.kindPicks && card.kindPicks.length) {
      setCutout(card, true);
      pickIn(card.kindPicks, "cutout", 1);
    }
    showTab("image");
    card.el.scrollIntoView({ behavior: "smooth", block: "start" });
    showToast(t("Tap Go and pick your favourite! ✨"), { ms: 7000 });
  }

  // Down here, not up with the other startup calls: meChip and friends are
  // `var`s assigned in this block, and a listener attached before that ran
  // would be attached to undefined.
  loadWho();
  if (meChip) meChip.addEventListener("click", showPicker);

  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-action]");
    // Disarm on a tap anywhere *outside* the armed button. It used to compare
    // against the [data-action] element under the tap, and the two "Goodbye"
    // buttons have no data-action - so the very tap that armed one of them
    // disarmed it again on the way up to the document, and it could never be
    // tapped a second time. It looked like a button that did nothing.
    if (armed && !armed.contains(event.target)) disarm();
    if (!target) return;
    var action = target.dataset.action;

    if (action === "clear-source") {
      clearSource();
      return;
    }
    if (action === "clear-text") { return; }   // handled on the element itself
    if (action === "open-mewiz") { openWizard(); return; }
    if (action === "close-mewiz") { closeWizard(); return; }
    if (action === "mewiz-go") { wizardGo(); return; }
    if (action === "me-emoji") {
      var picks = document.getElementById("me-emoji-picks");
      picks.hidden = !picks.hidden;
      return;
    }
    if (action === "me-clear") {
      if (!me) return;
      fetch("/api/profiles/" + encodeURIComponent(me.id) + "/avatar", { method: "DELETE" })
        .then(function () { faceVersion = Date.now(); loadWho(); })
        .catch(function () {});
      return;
    }
    if (action === "clear-say") {
      if (video.say) { video.say.value = ""; video.say.dispatchEvent(new Event("input")); video.say.focus(); }
      return;
    }
    if (action === "reset-styles") {
      // Whichever card the button is in - it used to always clear the
      // picture card's, even from the video card.
      var owner = target.closest(".card");
      if (owner) resetStyles(cards[owner.dataset.kind]);
      return;
    }
    if (action === "animate-item") {
      if (viewing && viewing.media === "image") {
        var picked = viewing;
        closeGallery();
        pickSource({ galleryId: picked.id }, fileUrl(picked));
      }
      return;
    }
    if (action === "make-character") { makeCharacter(); return; }
    if (action === "add-voice") { if (viewing && viewing.media === "video") openVoice(viewing); return; }
    if (action === "close-voice") { closeVoice(); return; }
    if (action === "discard-voice") { recorded = null; closeVoice(true); return; }
    if (action === "make-again") {
      if (viewing) makeAnother(viewing);
      return;
    }
    if (action === "tweak") { if (viewing) tweakItem(viewing); return; }
    if (action === "make-sticker") { makeSticker(); return; }
    if (action === "make-smooth") { makeSmooth(false); return; }
    if (action === "make-slow") { makeSmooth(true); return; }
    if (action === "make-huge") { makeHuge(); return; }
    if (action === "make-loop") {
      if (viewing && viewing.media === "video") openLooper(viewing);
      return;
    }
    if (action === "close-looper") { closeLooper(); return; }
    if (action === "change-picture") { if (viewing) openChange(viewing); return; }
    if (action === "close-change") { closeChange(); return; }
    if (action === "turn-into") { if (viewing) openRestyle(viewing); return; }
    if (action === "close-restyle") { closeRestyle(); return; }
    if (action === "see-outside") { if (viewing) openOutside(viewing); return; }
    if (action === "close-outside") { closeOutside(); return; }
    if (action === "fix-a-bit") { if (viewing) fixThisBit(viewing); return; }
    if (action === "use-mask") { sendMask(); return; }
    if (action === "use-as-banner") { if (viewing) useAsBanner(viewing.id, target); return; }
    if (action === "use-as-face") { if (viewing) useAsFace(viewing.id, target); return; }
    if (action === "reset-banner") { resetBanner(target); return; }
    if (action === "add-sound") {
      if (viewing && viewing.media === "video") openSounds(viewing);
      return;
    }
    if (action === "close-sounds") { closeSounds(); return; }
    if (action === "grab-frame") {
      if (viewing && viewing.media === "video") openFramer(viewing);
      return;
    }
    if (action === "close-framer") { closeFramer(); return; }
    if (action === "compare-picked") {
      var two = chosenItems();
      if (two.length === 2) openCompare(two[0], two[1]);
      return;
    }
    if (action === "close-compare") { closeCompare(); return; }
    if (action === "close-nowsheet") { closeNowSheet(); return; }
    if (action === "close-castsheet") { closeCastSheet(); return; }
    if (action === "pick-slot") {
      var which = target.dataset.slot === "last" ? "last" : "first";
      openGallery({
        title: which === "first" ? t("Pick where it starts") : t("Pick where it ends"),
        pick: function (item) { setSlot(which, item); showTab("video"); },
      });
      return;
    }
    if (action === "clear-slot") { setSlot(target.dataset.slot === "last" ? "last" : "first", null); return; }
    // The Picture card's other way in. The photo button beside it uploads one
    // and opens it; this one skips the upload for a picture that is already
    // theirs. Both end in the viewer, because that is where "Turn it into...",
    // "Change this picture", the two outpaint/inpaint doors and "Animate this"
    // all live - a video or a song has none of those, so neither is offered.
    if (action === "pick-start") {
      openGallery({
        only: function (item) { return item.media === "image"; },
        pick: function (item) { openViewerById(item.id); },
      });
      return;
    }
    if (action === "what-next") {
      if (viewing && viewing.media === "video") {
        var clip = viewing;
        closeGallery();
        pickSource({ galleryId: clip.id },
          "/api/gallery/" + encodeURIComponent(clip.id) + "/last-frame?v=" + clip.version);
        video.textarea.value = "";
        if (video.syncClear) video.syncClear();
        if (video.rememberText) video.rememberText();
        video.helperMsg.textContent = t("This starts where that video stopped. What happens next?");
        video.helperMsg.hidden = false;
      }
      return;
    }
    if (action === "share-item") {
      if (viewing) shareUrl(fileUrl(viewing), viewing.id, target);
      return;
    }
    if (action === "toggle-fav") { toggleFavourite(); return; }
    if (action === "toggle-family") { toggleFamily(); return; }
    if (action === "restore-item") { restoreViewing(); return; }
    if (action === "destroy-item") {
      if (arm(target, t("Really delete forever?"))) destroyViewing();
      return;
    }
    if (action === "open-draw") { openDraw(null); return; }
    if (action === "draw-on-item") {
      if (viewing && viewing.media === "image") {
        var base = fileUrl(viewing);
        closeGallery();
        openDraw(base);
      }
      return;
    }
    if (action === "print-item") { window.print(); return; }
    if (action === "make-card") { if (viewing && viewing.media === "image") openCardMaker(viewing); return; }
    if (action === "close-card") { closeCardMaker(); return; }
    if (action === "card-go") { saveCard(); return; }
    if (action === "tag-picked") { tagPicked(); return; }
    if (action === "join-picked") { openJoin(); return; }
    if (action === "close-join") { closeJoin(); return; }
    if (action === "join-go") { joinGoNow(); return; }
    if (action === "close-draw") { closeDraw(); return; }
    if (action === "use-drawing") { useDrawing(); return; }
    if (action === "draw-undo") { drawUndo(); return; }
    if (action === "draw-clear") { drawClear(true); return; }
    if (action === "draw-eraser") { setEraser(!erasing); return; }
    if (action === "close-gallery") { backToMine(); return; }
    if (action === "close-viewer") {
      // Back where they came from: the picker if they were in the middle of
      // picking something, and the Gallery page otherwise.
      if (viewerFromPicker && picking) {
        openGallery({ pick: picking, only: pickOnly, title: galleryTitle.textContent });
      } else {
        backToMine();
      }
      return;
    }
    if (action === "delete-item") {
      if (arm(target, t("Really delete it?"))) deleteViewing();
      return;
    }
    if (action === "toggle-select") { setChoosing(!choosing); return; }
    if (action === "select-all") { chooseAllOrNone(); return; }
    if (action === "delete-picked") {
      if (!chosen.length) return;
      var question = chosen.length === 1
        ? t("Really delete it?")
        : t("Really delete all {n}?", { n: chosen.length });
      if (arm(target, question)) deleteChosen();
      return;
    }
    if (action === "save-picked") {
      // The <a download> does the work; just stop a tap with nothing chosen.
      if (!chosen.length) event.preventDefault();
      return;
    }
    var holder = target.closest(".card");
    if (!holder) return;
    var card = cards[holder.dataset.kind];
    if (!card) return;
    if (action === "go") submit(card);
    else if (action === "stop") stop(card);
    else if (action === "script") writeScript(card);
    else if (action === "surprise") surpriseMe(card);
    else if (action === "remix") remixIdea(card);
    else if (action === "see-character") openCastSheet(card.character);
    else if (action === "reset-card") {
      if (!hasTyped(card) || arm(target, t("Really clear it?"))) {
        disarm();
        resetCard(card);
        card.textarea.focus({ preventScroll: true });
      }
    }
  });
})();
