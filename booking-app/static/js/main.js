/* ── Dark mode ─────────────────────────────────────────── */
(function () {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
})();

document.addEventListener('DOMContentLoaded', function () {
    /* Theme toggle */
    const toggle = document.getElementById('themeToggle');
    if (toggle) {
        toggle.addEventListener('click', function () {
            const html = document.documentElement;
            const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
        });
    }

    /* Auto-dismiss alerts */
    document.querySelectorAll('.alert').forEach(function (el) {
        setTimeout(function () {
            el.style.transition = 'opacity .4s ease';
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 420);
        }, 4000);
    });

    /* ── Local-time display for book/confirmation pages ─── */
    document.querySelectorAll('[data-slot-utc]').forEach(function (root) {
        const utc = root.dataset.slotUtc;
        if (!utc) return;
        const userTz   = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const slotDate = new Date(utc);

        const localDate = slotDate.toLocaleDateString('en-US', {
            timeZone: userTz,
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
        const localTime = slotDate.toLocaleTimeString('en-US', {
            timeZone: userTz, hour: 'numeric', minute: '2-digit'
        });
        const tzShort = slotDate.toLocaleTimeString('en-US', {
            timeZone: userTz, timeZoneName: 'short'
        }).split(' ').pop();

        const dateEl = root.querySelector('[data-local-date]');
        const timeEl = root.querySelector('[data-local-time]');
        const tzEl   = root.querySelector('[data-local-tz]');

        if (dateEl) dateEl.textContent = localDate;
        if (timeEl) timeEl.textContent = localTime;
        if (tzEl)   tzEl.textContent   = tzShort;
    });

    /* ── Calendar ───────────────────────────────────────── */
    if (typeof SLOTS === 'undefined') return;

    const calGrid    = document.getElementById('calGrid');
    const monthLabel = document.getElementById('monthLabel');
    const prevBtn    = document.getElementById('prevMonth');
    const nextBtn    = document.getElementById('nextMonth');
    const noSlotsMsg = document.getElementById('noSlotsMsg');
    const slotsPanel = document.getElementById('slotsPanel');
    const slotsList  = document.getElementById('slotsList');
    const slotDateLb = document.getElementById('slotDateLabel');
    const backToCal  = document.getElementById('backToCal');
    const tzLabelEl  = document.getElementById('tzLabel');

    if (!calGrid) return;

    /* Detect visitor timezone */
    const userTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

    /* Display timezone label */
    if (tzLabelEl) {
        const tzShortSample = new Date().toLocaleTimeString('en-US', {
            timeZone: userTz, timeZoneName: 'short'
        }).split(' ').pop();
        tzLabelEl.textContent = `Times shown in your local time (${tzShortSample})`;
    }

    /* Build local-date groups from UTC timestamps */
    const slotsByDate = {};   /* { 'YYYY-MM-DD': [{id, localTime}] } */
    SLOTS.forEach(function (slot) {
        const d = new Date(slot.utc);
        const localDateKey = d.toLocaleDateString('en-CA', { timeZone: userTz }); /* YYYY-MM-DD */
        const localTime    = d.toLocaleTimeString('en-US', {
            timeZone: userTz, hour: 'numeric', minute: '2-digit'
        });
        if (!slotsByDate[localDateKey]) slotsByDate[localDateKey] = [];
        slotsByDate[localDateKey].push({ id: slot.id, localTime: localTime });
    });

    /* Local today at midnight (for comparison) */
    const todayKey = new Date().toLocaleDateString('en-CA', { timeZone: userTz });
    const todayParts = todayKey.split('-').map(Number);
    const localToday = new Date(todayParts[0], todayParts[1] - 1, todayParts[2]);

    /* 2-month navigation cap */
    const _cap = new Date(localToday.getFullYear(), localToday.getMonth() + 2, 1);
    const maxYear  = _cap.getFullYear();
    const maxMonth = _cap.getMonth();   /* 0-indexed: first month that is OFF-LIMITS */

    let curYear  = localToday.getFullYear();
    let curMonth = localToday.getMonth();
    let selectedDate = null;

    const MONTH_NAMES = [
        'January','February','March','April','May','June',
        'July','August','September','October','November','December'
    ];
    const DAY_NAMES = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

    function toKey(y, m, d) {
        return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }

    function friendlyDate(dateStr) {
        const [y, m, d] = dateStr.split('-').map(Number);
        const dt = new Date(y, m - 1, d);
        return `${DAY_NAMES[dt.getDay()]}, ${MONTH_NAMES[m - 1]} ${d}, ${y}`;
    }

    function renderCalendar(year, month) {
        calGrid.innerHTML = '';
        monthLabel.textContent = `${MONTH_NAMES[month]} ${year}`;

        const firstDay  = new Date(year, month, 1).getDay();
        const daysInMon = new Date(year, month + 1, 0).getDate();

        prevBtn.disabled = (year === localToday.getFullYear() && month === localToday.getMonth());
        nextBtn.disabled = (year > maxYear) || (year === maxYear && month >= maxMonth);

        let hasAnySlot = false;

        for (let i = 0; i < firstDay; i++) {
            const empty = document.createElement('div');
            empty.className = 'cal-cell empty';
            calGrid.appendChild(empty);
        }

        for (let d = 1; d <= daysInMon; d++) {
            const key  = toKey(year, month, d);
            const dt   = new Date(year, month, d);
            const cell = document.createElement('button');
            cell.textContent = d;
            cell.className   = 'cal-cell';

            const isPast     = dt < localToday;
            const hasSlots   = slotsByDate[key] && slotsByDate[key].length > 0;
            const isToday    = (key === todayKey);
            const isSelected = (key === selectedDate);

            if (isPast || !hasSlots) {
                cell.className += ' disabled';
                cell.disabled = true;
            } else {
                cell.className += ' available';
                hasAnySlot = true;
            }
            if (isToday)    cell.className += ' today';
            if (isSelected) cell.className += ' selected';

            cell.setAttribute(
                'aria-label',
                `${friendlyDate(key)}${hasSlots ? ', ' + slotsByDate[key].length + ' slots' : ''}`
            );

            cell.addEventListener('click', function () {
                selectedDate = key;
                showSlots(key);
                renderCalendar(curYear, curMonth);
            });

            calGrid.appendChild(cell);
        }

        noSlotsMsg.style.display = hasAnySlot ? 'none' : 'block';
    }

    function showSlots(dateKey) {
        const slots = slotsByDate[dateKey] || [];
        slotDateLb.textContent = friendlyDate(dateKey);
        slotsList.innerHTML = '';

        slots.forEach(function (slot) {
            const btn = document.createElement('a');
            btn.href      = `/book/${slot.id}`;
            btn.className = 'time-slot-btn';
            btn.innerHTML = `<span class="slot-time-txt">${slot.localTime}</span><span class="slot-confirm-txt">Confirm →</span>`;
            slotsList.appendChild(btn);
        });

        if (window.innerWidth < 900) {
            document.querySelector('.calendar-panel').style.display = 'none';
            slotsPanel.style.display = 'flex';
        } else {
            slotsPanel.style.display = 'flex';
        }
    }

    function hideSlots() {
        selectedDate = null;
        slotsPanel.style.display = 'none';
        document.querySelector('.calendar-panel').style.display = '';
        renderCalendar(curYear, curMonth);
    }

    prevBtn.addEventListener('click', function () {
        if (curMonth === 0) { curMonth = 11; curYear--; }
        else curMonth--;
        renderCalendar(curYear, curMonth);
    });

    nextBtn.addEventListener('click', function () {
        let ny = curYear, nm = curMonth + 1;
        if (nm > 11) { nm = 0; ny++; }
        if (ny > maxYear || (ny === maxYear && nm >= maxMonth)) return;
        curYear = ny; curMonth = nm;
        renderCalendar(curYear, curMonth);
    });

    backToCal.addEventListener('click', hideSlots);

    renderCalendar(curYear, curMonth);
});
