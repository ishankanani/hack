(function () {
  "use strict";
  var C = window.INVITE;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var initials = function (n) { return n.split(/\s+/).map(function (w) { return w[0]; }).join("").slice(0, 2).toUpperCase(); };
  var at = new Date(C.weddingAt);
  var tz = { timeZone: "Asia/Kolkata" };

  /* ---------- simple bindings ---------- */
  var derived = {
    dateLong: at.toLocaleDateString("en-GB", Object.assign({ weekday: "long", day: "numeric", month: "long", year: "numeric" }, tz)),
    dateShort: at.toLocaleDateString("en-GB", Object.assign({ day: "numeric", month: "long", year: "numeric" }, tz)),
    time: at.toLocaleTimeString("en-US", Object.assign({ hour: "numeric", minute: "2-digit" }, tz)) + " onwards",
    couple: C.groom.first + " & " + C.bride.first,
    coupleCaps: C.groom.first + " & " + C.bride.first,
    monogram: C.groom.first[0] + "&" + C.bride.first[0],
    mainVenue: C.mainVenue,
    hashtag: C.hashtag,
  };
  document.querySelectorAll("[data-bind]").forEach(function (el) {
    var k = el.getAttribute("data-bind");
    var v = k.indexOf(".") > 0 ? k.split(".").reduce(function (o, p) { return o && o[p]; }, C) : derived[k];
    el.textContent = v || "";
  });

  /* ---------- intro: garlands + door ---------- */
  function garland(x, len, delay) {
    var h = '<div class="garland" style="left:' + x + '%;animation-delay:' + delay + 's">';
    for (var i = 0; i < len; i++) {
      if (i % 4 === 3) h += '<span class="g-leaf"></span>';
      else h += '<span class="g-bud ' + (i % 4 === 1 ? "g-bud--w" : "") + '"></span>';
    }
    return h + '<span class="g-lamp"></span></div>';
  }
  $("#garlands").innerHTML = garland(5, 15, 0) + garland(18, 10, 0.6) + garland(78, 10, 0.3) + garland(91, 15, 0.9);
  document.querySelectorAll(".door__grid").forEach(function (g) { g.innerHTML = new Array(15).join("<i></i>"); });

  function plant(dark) {
    var g1 = dark ? "#2d5a1c" : "#4caf3a", g2 = dark ? "#173a0e" : "#21701f", rib = dark ? "#5c7a2a" : "#b8d86a";
    var leaf = "M0 0 C40 -34 120 -44 175 -12 C120 2 50 12 0 5Z", ang = [-160, -128, -96, -62, -30, 2, 22];
    var s = '<svg viewBox="0 0 220 420" aria-hidden="true"><defs><linearGradient id="lf' + (dark ? "d" : "l") + '" x1="0" x2="1"><stop offset="0" stop-color="' + g2 + '"/><stop offset="1" stop-color="' + g1 + '"/></linearGradient></defs>';
    s += '<path d="M104 420 Q98 320 106 210 L116 210 Q114 320 120 420Z" fill="' + (dark ? "#3a2a12" : "#6c8a3a") + '"/>';
    ang.forEach(function (a, i) {
      var sc = 0.75 + (i % 3) * 0.15;
      s += '<g transform="translate(111 ' + (210 + (i % 2) * 14) + ') rotate(' + a + ') scale(' + sc + ')"><path d="' + leaf + '" fill="url(#lf' + (dark ? "d" : "l") + ')"/><path d="M0 2 C60 -20 120 -26 175 -12" stroke="' + rib + '" stroke-width="2" fill="none"/></g>';
    });
    return s + "</svg>";
  }
  document.querySelectorAll("[data-plant]").forEach(function (el) { el.innerHTML = plant(el.getAttribute("data-plant") === "dark"); });

  var opened = false;
  function openDoors() {
    if (opened) return; opened = true;
    var intro = $("#intro");
    intro.classList.add("open");
    setTimeout(function () { intro.classList.add("gone"); document.body.classList.remove("locked"); startPetals(); }, 1700);
    setTimeout(function () { intro.remove(); }, 2700);
  }
  $("#intro").addEventListener("click", openDoors);

  /* ---------- gopuram (procedural SVG) ---------- */
  (function () {
    var W = 300, H = 380, tiers = 9, base = 260, top = 110, tierH = 26, y = 0;
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" aria-hidden="true"><defs>' +
      '<linearGradient id="gStone" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#efd9b4"/><stop offset="1" stop-color="#cdb08a"/></linearGradient>' +
      '<radialGradient id="gDoor" cx=".5" cy=".7" r=".7"><stop offset="0" stop-color="#fff3c4"/><stop offset=".5" stop-color="#f2b54a"/><stop offset="1" stop-color="#8a4b12"/></radialGradient></defs>';
    var cols = ["#e86a8a", "#3a8fd0", "#f0b43c", "#4fb79a"];
    // crown (barrel vault + kalasams)
    var cw = top - 10, cx = (W - cw) / 2;
    s += '<rect x="' + cx + '" y="18" width="' + cw + '" height="20" rx="9" fill="#e86a8a" stroke="#b5384e" stroke-width="1.5"/>';
    for (var k = 0; k < 9; k++) {
      var kx = cx + 6 + k * ((cw - 12) / 8);
      s += '<path d="M' + kx + ' 18 q-4 -6 0 -12 q4 6 0 12z" fill="#e7b23e"/><circle cx="' + kx + '" cy="5" r="1.6" fill="#e7b23e"/>';
    }
    s += '<path d="M' + (cx - 6) + ' 38 q-6 -18 6 -24 M' + (cx + cw + 6) + ' 38 q6 -18 -6 -24" stroke="#2f86b8" stroke-width="4" fill="none" stroke-linecap="round"/>';
    s += '<path d="M150 0 v-0" /><line x1="150" y1="-6" x2="150" y2="6" stroke="#6b3a1a"/>';
    y = 38;
    for (var t = 0; t < tiers; t++) {
      var w1 = top + (base - top) * (t / tiers), w2 = top + (base - top) * ((t + 1) / tiers);
      var x1 = (W - w1) / 2, x2 = (W - w2) / 2;
      s += '<path d="M' + x1 + " " + y + " L" + (x1 + w1) + " " + y + " L" + (x2 + w2) + " " + (y + tierH) + " L" + x2 + " " + (y + tierH) + 'Z" fill="url(#gStone)"/>';
      s += '<rect x="' + (x2 - 2) + '" y="' + (y + tierH - 5) + '" width="' + (w2 + 4) + '" height="5" fill="' + cols[t % 4] + '"/>';
      var n = Math.floor(w1 / 16);
      for (var j = 0; j < n; j++) {
        var nx = x1 + 4 + j * ((w1 - 8) / n), nw = (w1 - 8) / n - 3, c = cols[(j + t) % 4];
        var mid = Math.abs(j - (n - 1) / 2) < 1;
        s += '<path d="M' + nx + " " + (y + tierH - 6) + " v-10 q" + nw / 2 + " -8 " + nw + " 0 v10z" + '" fill="' + (mid ? "#3b1a0c" : c) + '" opacity="' + (mid ? 1 : 0.85) + '"/>';
        if (!mid) s += '<circle cx="' + (nx + nw / 2) + '" cy="' + (y + 7) + '" r="1.6" fill="#f4d27a"/>';
      }
      y += tierH;
    }
    // base with doorway
    var bx = (W - base) / 2, bh = H - y - 18;
    s += '<rect x="' + bx + '" y="' + y + '" width="' + base + '" height="' + bh + '" fill="url(#gStone)"/>';
    for (var p = 0; p < 12; p++) s += '<rect x="' + (bx + 6 + p * (base - 12) / 12) + '" y="' + (y + 6) + '" width="6" height="' + (bh - 12) + '" fill="#bf9c72" opacity=".55"/>';
    s += '<path d="M128 ' + (y + bh) + " V" + (y + 18) + " q22 -14 44 0 V" + (y + bh) + 'Z" fill="url(#gDoor)" stroke="#8a5a2a" stroke-width="2"/>';
    // steps
    for (var st = 0; st < 4; st++) s += '<rect x="' + (110 - st * 10) + '" y="' + (y + bh + st * 4.5) + '" width="' + (80 + st * 20) + '" height="4.5" fill="' + (st % 2 ? "#e2cba6" : "#d4b98f") + '"/>';
    // lamps
    [bx - 6, bx + base - 6].forEach(function (lx) {
      s += '<rect x="' + (lx + 5) + '" y="' + (y + 14) + '" width="2" height="' + (bh - 10) + '" fill="#c79a3a"/><ellipse cx="' + (lx + 6) + '" cy="' + (y + 14) + '" rx="7" ry="2.5" fill="#d9a83e"/><path d="M' + (lx + 6) + " " + (y + 3) + ' q3 5 0 9 q-3 -4 0 -9z" fill="#ffcf4a" class="flame"/>';
    });
    s += '<rect x="148" y="-2" width="2" height="0"/><path d="M151 0 v-14 l12 4 -12 4" fill="#c4262e" stroke="#6b3a1a" transform="translate(0,4)"/>';
    $("#gopuram").innerHTML = s + "</svg>";
  })();

  /* ---------- petals ---------- */
  function startPetals() {
    var box = $("#petals"), reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    for (var i = 0; i < 16; i++) {
      var p = document.createElement("span");
      p.className = "petal";
      var size = 8 + Math.random() * 12;
      p.style.cssText = "left:" + Math.random() * 100 + "%;width:" + size + "px;height:" + size * 0.8 + "px;animation-duration:" + (9 + Math.random() * 9) + "s," + (3 + Math.random() * 3) + "s;animation-delay:-" + Math.random() * 15 + "s";
      box.appendChild(p);
    }
  }

  /* ---------- countdown ---------- */
  function tick() {
    var d = Math.max(0, at - new Date()), u = { d: 864e5, h: 36e5, m: 6e4, s: 1e3 }, v = {};
    v.d = Math.floor(d / u.d); v.h = Math.floor(d % u.d / u.h); v.m = Math.floor(d % u.h / u.m); v.s = Math.floor(d % u.m / u.s);
    Object.keys(v).forEach(function (k) { var el = $('[data-c="' + k + '"]'); var t = String(v[k]).padStart(2, "0"); if (el.textContent !== t) { el.textContent = t; el.classList.remove("flip"); void el.offsetWidth; el.classList.add("flip"); } });
  }
  tick(); setInterval(tick, 1000);

  /* ---------- scratch card ---------- */
  (function () {
    var cv = $("#scratchCanvas"), ctx = cv.getContext("2d"), done = false, drawing = false, last = null;
    function paint() {
      var r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      cv.width = r.width * dpr; cv.height = r.height * dpr; ctx.scale(dpr, dpr);
      var g = ctx.createLinearGradient(0, 0, r.width, r.height);
      g.addColorStop(0, "#7d2e1c"); g.addColorStop(0.55, "#a8622a"); g.addColorStop(1, "#d39a3a");
      ctx.fillStyle = g; ctx.fillRect(0, 0, r.width, r.height);
      ctx.fillStyle = "rgba(255,230,180,.22)";
      for (var x = 8; x < r.width; x += 14) for (var y = 8; y < r.height; y += 14) { ctx.beginPath(); ctx.arc(x, y, 1.4, 0, 7); ctx.fill(); }
      ctx.globalCompositeOperation = "destination-out"; ctx.lineCap = "round"; ctx.lineWidth = 38;
    }
    function pos(e) { var r = cv.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    function check() {
      var d = ctx.getImageData(0, 0, cv.width, cv.height).data, clear = 0, n = 0;
      for (var i = 3; i < d.length; i += 64) { n++; if (d[i] === 0) clear++; }
      if (clear / n > 0.45) reveal();
    }
    function reveal() { if (done) return; done = true; cv.classList.add("gone"); $("#scratchHint").hidden = true; $("#revealBtn").hidden = true; burst(); }
    cv.addEventListener("pointerdown", function (e) { drawing = true; last = pos(e); cv.setPointerCapture(e.pointerId); $("#scratchHint").classList.add("fade"); });
    cv.addEventListener("pointermove", function (e) { if (!drawing || done) return; var p = pos(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; });
    cv.addEventListener("pointerup", function () { drawing = false; check(); });
    $("#revealBtn").addEventListener("click", reveal);
    requestAnimationFrame(paint);
  })();
  function burst() {
    var host = $(".scratch__inner");
    for (var i = 0; i < 24; i++) {
      var b = document.createElement("span"); b.className = "confetti";
      b.style.setProperty("--x", (Math.random() * 2 - 1) * 140 + "px");
      b.style.setProperty("--y", -(40 + Math.random() * 120) + "px");
      b.style.background = ["#f2c14e", "#e05a7a", "#fff1c9", "#c4262e"][i % 4];
      host.appendChild(b); setTimeout(b.remove.bind(b), 1400);
    }
  }

  /* ---------- portraits ---------- */
  function portrait(person, cls) {
    var inner = person.photo ? '<img src="' + esc(person.photo) + '" alt="' + esc(person.name || person.full) + '" loading="lazy"/>' : '<span class="frame__mono">' + esc(initials(person.full || person.name)) + "</span>";
    return '<div class="frame ' + (cls || "") + '"><div class="frame__crown"></div><div class="frame__arch">' + inner + '</div><div class="frame__base"></div></div>';
  }
  $("#couple").innerHTML = [["The Groom", C.groom], ["The Bride", C.bride]].map(function (r) {
    return '<div class="person reveal">' + portrait(r[1]) + '<div class="person__role">' + r[0] + '</div><div class="person__name">' + esc(r[1].full) + '</div><div class="person__par">' + esc(r[1].parents) + "</div></div>";
  }).join('<div class="couple__amp script">&amp;</div>');

  $("#family").innerHTML = [["The Groom's Family", C.family.groom], ["The Bride's Family", C.family.bride]].map(function (g) {
    return '<div class="fam reveal"><div class="fam__h script"><span>' + g[0] + "</span></div>" + g[1].map(function (m) {
      return '<div class="member">' + portrait(m, "frame--sm") + '<div class="ribbon">' + esc(m.role) + '</div><div class="member__name">' + esc(m.name) + "</div></div>";
    }).join("") + "</div>";
  }).join("");

  /* ---------- rituals ---------- */
  var nums = ["One", "Two", "Three", "Four", "Five", "Six", "Seven"];
  $("#ritualsSub").textContent = (nums[C.events.length - 1] || C.events.length) + " days of sacred rituals";
  $("#rituals").innerHTML = '<div class="rituals__line"></div>' + C.events.map(function (e, i) {
    return '<div class="ritual ' + (i % 2 ? "ritual--r" : "ritual--l") + ' reveal"><span class="ritual__lotus"></span><div class="leaf"><div class="leaf__body">' +
      '<div class="leaf__k">Event ' + (i + 1) + '</div><div class="leaf__ic">' + e.icon + '</div><div class="leaf__name">' + esc(e.name) + "</div>" +
      (e.note ? '<div class="leaf__note">' + esc(e.note) + "</div>" : "") +
      '<div class="leaf__orn">✦</div><div class="leaf__row">🕰 ' + esc(e.date) + '</div><div class="leaf__row">⌖ ' + esc(e.venue) + "</div>" +
      '<div class="leaf__dk">Dress code</div><div class="leaf__dress">👘 ' + esc(e.dress) + "</div></div></div></div>";
  }).join("");

  /* ---------- story ---------- */
  $("#story").innerHTML = C.story.map(function (s, i) {
    return '<div class="story__item reveal"><div class="story__num">' + (i + 1) + '</div><div class="story__card"><span class="story__when">♥ ' + esc(s.when) + '</span><h4>' + esc(s.title) + "</h4><p>" + esc(s.text) + "</p></div></div>";
  }).join("");

  /* ---------- coverflow ---------- */
  (function () {
    var G = C.gallery, cur = 0, track = $("#flowTrack");
    var hues = [[350, 20], [28, 45], [160, 120], [280, 330], [12, 350]];
    function art(g, i) {
      if (g.photo) return '<img src="' + esc(g.photo) + '" alt="' + esc(g.caption) + '" loading="lazy"/>';
      var h = hues[i % hues.length];
      return '<div class="ph" style="--a:hsl(' + h[0] + ',62%,38%);--b:hsl(' + h[1] + ',70%,62%)"><span class="ph__mono">' + esc(derived.monogram) + '</span><span class="ph__t">' + esc(g.caption) + "</span></div>";
    }
    track.innerHTML = G.map(function (g, i) { return '<div class="flow__slide" data-i="' + i + '">' + art(g, i) + '<span class="flow__zoom">⤢</span></div>'; }).join("");
    $("#flowDots").innerHTML = G.map(function (_, i) { return '<button aria-label="Photo ' + (i + 1) + '" data-i="' + i + '"></button>'; }).join("");
    var slides = track.children, dots = $("#flowDots").children;
    function render() {
      for (var i = 0; i < slides.length; i++) {
        var o = i - cur, a = Math.abs(o);
        slides[i].style.transform = "translateX(" + o * 58 + "%) translateZ(" + -a * 90 + "px) rotateY(" + -Math.sign(o) * Math.min(a, 1) * 38 + "deg)";
        slides[i].style.zIndex = 10 - a; slides[i].style.opacity = a > 2 ? 0 : 1 - a * 0.25;
        slides[i].classList.toggle("on", o === 0);
        dots[i].classList.toggle("on", o === 0);
      }
      $("#flowCap").textContent = G[cur].caption; $("#flowSub").textContent = G[cur].sub || "";
    }
    function go(d) { cur = (cur + d + G.length) % G.length; render(); }
    $("#flowPrev").onclick = function () { go(-1); }; $("#flowNext").onclick = function () { go(1); };
    $("#flowDots").onclick = function (e) { var i = e.target.getAttribute("data-i"); if (i != null) { cur = +i; render(); } };
    var sx = null;
    track.addEventListener("pointerdown", function (e) { sx = e.clientX; });
    track.addEventListener("pointerup", function (e) {
      if (sx == null) return; var dx = e.clientX - sx; sx = null;
      if (Math.abs(dx) > 35) return go(dx < 0 ? 1 : -1);
      var s = e.target.closest(".flow__slide"); if (!s) return;
      var i = +s.getAttribute("data-i");
      if (i !== cur) { cur = i; render(); } else { $("#lbImg").innerHTML = art(G[i], i); $("#lightbox").hidden = false; }
    });
    $("#lightbox").onclick = function () { this.hidden = true; };
    render();
  })();

  /* ---------- venues ---------- */
  $("#venues").innerHTML = C.venues.map(function (v) {
    var q = encodeURIComponent(v.name + ", " + v.address);
    return '<div class="leafcard venue reveal"><div class="script venue__ev">' + esc(v.events) + '</div><div class="venue__name">' + esc(v.name) + '</div><div class="leaf__orn">❖</div>' +
      '<div class="info"><span class="info__ic">⌖</span><div><div class="info__k">Address</div><div class="info__v">' + esc(v.address) + "</div></div></div>" +
      '<div class="info"><span class="info__ic">▦</span><div><div class="info__k">' + esc(v.scheduleLabel || "Schedule") + '</div><div class="info__v">' + esc(v.schedule) + "</div></div></div>" +
      '<a class="btn-red" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + q + '">➤ Get Directions ›</a>' +
      '<div class="map"><iframe title="Map of ' + esc(v.name) + '" loading="lazy" referrerpolicy="no-referrer-when-downgrade" src="https://maps.google.com/maps?q=' + q + '&z=15&output=embed"></iframe>' +
      '<div class="map__pin"><span>📍</span><div><b>' + esc(v.name) + "</b><small>" + esc(v.address) + "</small></div></div></div></div>";
  }).join("");

  /* ---------- RSVP ---------- */
  var guests = 1;
  document.querySelectorAll(".step").forEach(function (b) {
    b.onclick = function () { guests = Math.min(20, Math.max(1, guests + +b.getAttribute("data-d"))); $("#gCount").textContent = guests; };
  });
  document.querySelectorAll('input[name="attend"]').forEach(function (r) {
    r.onchange = function () { $("#guestsWrap").classList.toggle("off", r.value === "no" && r.checked); };
  });
  $("#rsvp").addEventListener("submit", function (e) {
    e.preventDefault();
    var name = $("#rName").value.trim(), yes = $('input[name="attend"]:checked').value === "yes", msg = $("#rMsg").value.trim();
    var text = "RSVP for " + derived.couple + "'s wedding\nName: " + name + "\n" + (yes ? "Attending ✅ · Guests: " + guests : "Unable to attend 🙏") + (msg ? "\nBlessings: " + msg : "");
    if (msg) addWish({ text: msg, by: name });
    var done = $("#rsvpDone");
    done.hidden = false;
    done.innerHTML = (yes ? "Thank you, " + esc(name) + "! We can't wait to celebrate with you." : "Thank you, " + esc(name) + ". You'll be with us in spirit.") +
      '<a class="btn-green" target="_blank" rel="noopener" href="https://wa.me/' + esc(C.rsvpWhatsApp) + "?text=" + encodeURIComponent(text) + '">Send via WhatsApp</a>';
    done.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  /* ---------- wishes wall (saved on this device) ---------- */
  var KEY = "invite-wishes";
  function stored() { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; } }
  function renderWishes() {
    $("#wishList").innerHTML = stored().concat(C.wishes).map(function (w) { return '<div class="wish"><p>“' + esc(w.text) + '”</p><span>— ' + esc(w.by) + "</span></div>"; }).join("");
  }
  function addWish(w) { var s = stored(); s.unshift(w); try { localStorage.setItem(KEY, JSON.stringify(s.slice(0, 30))); } catch (e) {} renderWishes(); }
  $("#wishForm").addEventListener("submit", function (e) {
    e.preventDefault(); addWish({ text: $("#wMsg").value.trim(), by: $("#wName").value.trim() }); this.reset(); toast("Thank you for your wishes 🌸");
  });
  renderWishes();

  /* ---------- contacts + closing ---------- */
  var ICON_PHONE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></svg>';
  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.4 8.4 0 0 1-12.4 7.4L3 21l2.1-5.4A8.4 8.4 0 1 1 21 11.5z"/></svg>';
  function miniGopuram(x, w, h, col) {
    var s = "", tiers = 6, th = h / (tiers + 1);
    for (var t = 0; t < tiers; t++) {
      var tw = w * (0.45 + 0.55 * (t / tiers)), tx = x + (w - tw) / 2, ty = 90 - h + th * (t + 1);
      s += '<rect x="' + tx + '" y="' + ty + '" width="' + tw + '" height="' + (th - 1) + '" fill="' + col + '"/>';
    }
    return s + '<rect x="' + (x + w * 0.3) + '" y="' + (90 - h) + '" width="' + w * 0.4 + '" height="' + th + '" rx="' + th / 2 + '" fill="' + col + '"/>';
  }
  $("#contacts").innerHTML = C.contacts.map(function (c) {
    var tel = c.phone.replace(/[^\d+]/g, ""), wa = tel.replace(/\D/g, "");
    return '<div class="fam__h script"><span>' + esc(c.side) + '</span></div><div class="contact reveal"><div class="contact__av">' + esc(initials(c.name)) + '</div><div class="contact__b"><b>' + esc(c.name) + "</b><small>" + esc(c.role) + "</small><span>" + esc(c.phone) + '</span></div><div class="contact__a"><a href="tel:' + tel + '" aria-label="Call ' + esc(c.name) + '">' + ICON_PHONE + '</a><a class="wa" target="_blank" rel="noopener" href="https://wa.me/' + wa + '" aria-label="WhatsApp ' + esc(c.name) + '">' + ICON_CHAT + "</a></div></div>";
  }).join("");
  $("#closingFam").innerHTML = esc(C.groom.family) + " Family<br><em class='script'>&amp;</em><br>" + esc(C.bride.family) + " Family";
  $("#tagBtn").onclick = function () { (navigator.clipboard ? navigator.clipboard.writeText(C.hashtag) : Promise.reject()).then(function () { toast("Copied " + C.hashtag); }, function () {}); };
  $("#closingTemples").innerHTML = '<svg viewBox="0 0 400 90" preserveAspectRatio="xMidYMax meet" aria-hidden="true">' +
    miniGopuram(18, 70, 78, "#c48a4a") + miniGopuram(312, 70, 82, "#c48a4a") + miniGopuram(170, 60, 56, "#a8703a") +
    '<path d="M0 90 V74 H110 V66 H290 V74 H400 V90Z" fill="#8c5a2b"/><g fill="#3f7a3a"><circle cx="120" cy="64" r="12"/><circle cx="140" cy="68" r="9"/><circle cx="262" cy="66" r="11"/><circle cx="285" cy="70" r="8"/><circle cx="8" cy="72" r="10"/><circle cx="394" cy="70" r="10"/></g></svg>';

  /* ---------- helpers ---------- */
  var tt;
  function toast(m) { var t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(tt); tt = setTimeout(function () { t.hidden = true; }, 2200); }

  // scroll reveal
  var io = "IntersectionObserver" in window ? new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }); }, { threshold: 0.15 }) : null;
  document.querySelectorAll(".reveal, .sec > .title, .sec > .sub, .parchment, .count, .scratch").forEach(function (el) { el.classList.add("reveal"); io ? io.observe(el) : el.classList.add("in"); });
})();
