// SprintBoard front-end: drag-and-drop for the planner and the sprint board.
(function () {
  const csrf = document.querySelector('meta[name=csrf]').content;

  async function post(url, data) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(res.status);
    } catch (err) {
      alert('That change could not be saved. The page will reload.');
      location.reload();
    }
  }

  const ids = (list) => [...list.children].map((li) => Number(li.dataset.id));
  const points = (list) => [...list.children].reduce((sum, li) => sum + Number(li.dataset.points || 0), 0);

  // Selects that submit their form as soon as they change
  document.querySelectorAll('select[data-autosubmit]').forEach((sel) =>
    sel.addEventListener('change', () => sel.form.submit()));

  // ---- Backlog and sprint planning
  const planner = document.getElementById('planner');
  if (planner) {
    const pid = planner.dataset.pid;
    const velocity = planner.dataset.velocity === '' ? null : Number(planner.dataset.velocity);

    function refreshTotals() {
      planner.querySelectorAll('.plan-card').forEach((card) => {
        const list = card.querySelector('.plan-list');
        const total = points(list);
        card.querySelector('.pts-total').textContent = total;
        const warn = card.querySelector('.cap-warn');
        if (warn) warn.hidden = !(velocity !== null && total > velocity);
      });
      const counter = planner.querySelector('[data-count-for=backlog]');
      if (counter) counter.textContent = document.getElementById('list-backlog').children.length;
    }
    refreshTotals();

    const payload = (list) => ({
      sprint_id: list.dataset.sprint === '' ? null : Number(list.dataset.sprint),
      task_ids: ids(list),
    });

    planner.querySelectorAll('.plan-list').forEach((list) => {
      new Sortable(list, {
        group: 'plan', animation: 150, handle: '.grip', ghostClass: 'ghost',
        onEnd(evt) {
          const lists = [payload(evt.to)];
          if (evt.from !== evt.to) lists.push(payload(evt.from));
          refreshTotals();
          post(`/api/p/${pid}/reorder`, { lists });
        },
      });
    });
  }

  // ---- Sprint board
  const board = document.getElementById('board');
  if (board) {
    const pid = board.dataset.pid;

    function refreshColumns() {
      board.querySelectorAll('.board-col').forEach((col) => {
        const list = col.querySelector('.board-list');
        col.querySelector('.col-count').textContent = list.children.length;
        col.querySelector('.col-points').textContent = points(list);
      });
    }

    board.querySelectorAll('.board-list').forEach((list) => {
      new Sortable(list, {
        group: 'board', animation: 150, ghostClass: 'ghost',
        onEnd(evt) {
          refreshColumns();
          post(`/api/p/${pid}/board`, {
            task_id: Number(evt.item.dataset.id),
            status: evt.to.dataset.status,
            order: ids(evt.to),
          });
        },
      });
    });
  }
})();
