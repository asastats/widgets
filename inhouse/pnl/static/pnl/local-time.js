/**
 * @file P&L: show "Transactions processed" in the reader's timezone and format.
 */
(function () {
  "use strict";

  /** Replace the server's UTC text of every `time[data-local-time]` in `root`. */
  function localize(root) {
    root.querySelectorAll("time[data-local-time]").forEach(function (element) {
      var date = new Date(element.getAttribute("datetime"));
      if (isNaN(date.getTime())) return;
      element.textContent = date.toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      });
    });
  }

  localize(document);
  document.body.addEventListener("htmx:after:swap", function () {
    localize(document);
  });
})();
