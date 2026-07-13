(function() {
  'use strict';

  function sumChildHeights(container, excludedSelector) {
    return Array.from(container.children).reduce(function(total, child) {
      if (excludedSelector && child.matches(excludedSelector)) { return total; }
      return total + child.getBoundingClientRect().height;
    }, 0);
  }

  function adjustParticipantRows() {
    var leftColumn = document.querySelector('.col-left');
    var middleColumn = document.querySelector('.col-mid');
    if (!leftColumn || !middleColumn) { return; }

    var rows = Array.from(leftColumn.querySelectorAll('[data-participant-row]'));
    var more = leftColumn.querySelector('[data-participant-more]');
    if (!rows.length || !more) { return; }

    rows.forEach(function(row) { row.classList.add('participant-hidden'); });

    // 临时显示一个参与者行和未展示提示，以获得 CSS 布局后的真实高度。
    rows[0].classList.remove('participant-hidden');
    var rowHeight = rows[0].getBoundingClientRect().height;
    rows[0].classList.add('participant-hidden');
    more.classList.remove('participant-hidden');
    var moreHeight = more.getBoundingClientRect().height;
    more.classList.add('participant-hidden');

    if (!rowHeight) { return; }

    var hud = middleColumn.querySelector('.hud-section');
    var fitting = middleColumn.querySelector('.fit-section');
    var middleContentHeight = (hud ? hud.getBoundingClientRect().height : 0)
      + (fitting ? sumChildHeights(fitting) : 0);
    var fixedLeftHeight = sumChildHeights(
      leftColumn,
      '[data-participant-row], [data-participant-more]'
    );
    var total = Number.parseInt(leftColumn.dataset.attackerTotal || rows.length, 10);
    var minimum = Number.parseInt(leftColumn.dataset.minParticipants || '15', 10);
    var reserveMore = total > minimum;
    var availableHeight = middleContentHeight - fixedLeftHeight - (reserveMore ? moreHeight : 0);
    var visible = Math.max(minimum, Math.floor(availableHeight / rowHeight));
    visible = Math.min(rows.length, visible);

    // 全部参与者都能展示时，不再为“未展示”提示预留高度。
    if (visible === rows.length && total <= rows.length) {
      visible = Math.min(rows.length, Math.max(minimum, Math.floor(
        (middleContentHeight - fixedLeftHeight) / rowHeight
      )));
    }

    rows.slice(0, visible).forEach(function(row) {
      row.classList.remove('participant-hidden');
    });

    var hidden = Math.max(0, total - visible);
    if (hidden > 0) {
      more.textContent = '还有 ' + hidden + ' 名参与者未展示';
      more.classList.remove('participant-hidden');
    }
  }

  // Replace broken images
  document.querySelectorAll('img').forEach(function(img) {
    img.addEventListener('error', function() {
      if (this.onerror) { this.onerror = null; }
    });
  });

  adjustParticipantRows();
  window.addEventListener('load', adjustParticipantRows, { once: true });
})();
