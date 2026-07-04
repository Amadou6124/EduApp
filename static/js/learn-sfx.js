/* learn-sfx.js — sons partagés du portail élève (Histoire / Quiz / Examen).
 * Joue un fichier self-hosté s'il existe (static/vendor/sfx/<name>.mp3),
 * sinon retombe sur un son synthétisé (Web Audio, zéro asset).
 * Muet global persistant (localStorage 'learn-muted').
 *
 * Usage :
 *   LearnSFX.init("/static/vendor/sfx/");   // une fois par page
 *   LearnSFX.play('correct'|'wrong'|'win'|'tap');
 *   LearnSFX.toggleMute();                    // -> nouveau bool muted
 */
(function () {
  var NAMES = ['correct', 'wrong', 'complete', 'tap'];
  var ALIAS = { success: 'correct', error: 'wrong', win: 'complete', complete: 'complete',
                correct: 'correct', wrong: 'wrong', tap: 'tap' };

  var SFX = {
    base: '', _cache: {}, _ac: null, _loaded: false,
    muted: (function () { try { return localStorage.getItem('learn-muted') === '1'; } catch (e) { return false; } })(),

    init: function (base) {
      if (this._loaded) return;
      this._loaded = true;
      this.base = base || '';
      var self = this;
      NAMES.forEach(function (n) {
        try {
          var a = new Audio(self.base + n + '.mp3');
          a.preload = 'auto'; a.volume = 0.5;
          a.addEventListener('canplaythrough', function () { self._cache[n] = a; }, { once: true });
          a.load();
        } catch (e) {}
      });
    },

    play: function (kind) {
      if (this.muted) return;
      var name = ALIAS[kind] || kind;
      var a = this._cache[name];
      if (a) {
        try { var c = a.cloneNode(true); c.volume = a.volume; var p = c.play(); if (p && p.catch) p.catch(function () {}); return; }
        catch (e) {}
      }
      this._synth(name);
    },

    _synth: function (name) {
      try {
        var ac = this._ac || (this._ac = new (window.AudioContext || window.webkitAudioContext)());
        if (ac.state === 'suspended') ac.resume();
        var now = ac.currentTime;
        var beep = function (f, t0, dur, type, g) {
          var o = ac.createOscillator(), ga = ac.createGain();
          o.type = type || 'sine'; o.frequency.value = f;
          ga.gain.setValueAtTime(0, now + t0);
          ga.gain.linearRampToValueAtTime(g || 0.06, now + t0 + 0.008);
          ga.gain.exponentialRampToValueAtTime(0.0001, now + t0 + dur);
          o.connect(ga); ga.connect(ac.destination);
          o.start(now + t0); o.stop(now + t0 + dur);
        };
        if (name === 'tap') beep(500, 0, 0.07, 'sine', 0.04);
        else if (name === 'correct') { beep(660, 0, 0.1, 'sine', 0.06); beep(880, 0.08, 0.16, 'sine', 0.06); }
        else if (name === 'wrong') beep(160, 0, 0.16, 'sawtooth', 0.04);
        else if (name === 'complete') { beep(660, 0, 0.12, 'sine', 0.06); beep(880, 0.1, 0.12, 'sine', 0.06); beep(1046, 0.2, 0.22, 'sine', 0.07); }
      } catch (e) {}
    },

    toggleMute: function () {
      this.muted = !this.muted;
      try { localStorage.setItem('learn-muted', this.muted ? '1' : '0'); } catch (e) {}
      return this.muted;
    }
  };

  window.LearnSFX = SFX;
})();
