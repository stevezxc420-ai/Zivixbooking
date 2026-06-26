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

    if (!calGrid) return;

    const today   = new Date();
    today.setHours(0, 0, 0, 0);
    let curYear   = today.getFullYear();
    let curMonth  = today.getMonth();     // 0-indexed
    let selectedDate = null;

    const MONTH_NAMES = [
        'January','February','March','April','May','June',
        'July','August','September','October','November','December'
    ];
    const DAY_NAMES = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

    function toKey(y, m, d) {
        return `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    }

    function friendlyDate(dateStr) {
        const [y, m, d] = dateStr.split('-').map(Number);
        const dt = new Date(y, m - 1, d);
        return `${DAY_NAMES[dt.getDay()]}, ${MONTH_NAMES[m-1]} ${d}, ${y}`;
    }

    function fmt12(timeStr) {
        const [h, min] = timeStr.split(':').map(Number);
        const period = h >= 12 ? 'PM' : 'AM';
        const hour12 = h % 12 || 12;
        return `${hour12}:${String(min).padStart(2,'0')} ${period}`;
    }

    function renderCalendar(year, month) {
        calGrid.innerHTML = '';
        monthLabel.textContent = `${MONTH_NAMES[month]} ${year}`;

        const firstDay  = new Date(year, month, 1).getDay();
        const daysInMon = new Date(year, month + 1, 0).getDate();

        /* Disable prev if already at current month */
        prevBtn.disabled = (year === today.getFullYear() && month === today.getMonth());

        let hasAnySlot = false;

        /* Empty cells before first day */
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

            const isPast      = dt < today;
            const hasSlots    = SLOTS[key] && SLOTS[key].length > 0;
            const isToday     = (dt.getTime() === today.getTime());
            const isSelected  = (key === selectedDate);

            if (isPast || !hasSlots) {
                cell.className += ' disabled';
                cell.disabled = true;
            } else {
                cell.className += ' available';
                hasAnySlot = true;
            }
            if (isToday)    cell.className += ' today';
            if (isSelected) cell.className += ' selected';

            cell.setAttribute('aria-label', `${friendlyDate(key)}${hasSlots ? ', ' + SLOTS[key].length + ' slots' : ''}`);

            cell.addEventListener('click', function () {
                selectedDate = key;
                showSlots(key);
                /* Re-render to update selected highlight */
                renderCalendar(curYear, curMonth);
            });

            calGrid.appendChild(cell);
        }

        noSlotsMsg.style.display = hasAnySlot ? 'none' : 'block';
    }

    function showSlots(dateKey) {
        const slots = SLOTS[dateKey] || [];
        slotDateLb.textContent = friendlyDate(dateKey);
        slotsList.innerHTML = '';

        slots.forEach(function (slot) {
            const btn = document.createElement('a');
            btn.href      = `/book/${slot.id}`;
            btn.className = 'time-slot-btn';
            btn.innerHTML = `<span class="slot-time-txt">${fmt12(slot.time)}</span><span class="slot-confirm-txt">Confirm →</span>`;
            slotsList.appendChild(btn);
        });

        /* On mobile: hide calendar, show panel */
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
        if (curMonth === 11) { curMonth = 0; curYear++; }
        else curMonth++;
        renderCalendar(curYear, curMonth);
    });

    backToCal.addEventListener('click', hideSlots);

    /* Initial render */
    renderCalendar(curYear, curMonth);
});
