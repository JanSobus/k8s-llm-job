// Minimal local HTMX-compatible behavior for this demo.
// Supports hx-get, hx-post, hx-trigger load/every, hx-target, hx-swap, hx-include,
// and hx-encoding="multipart/form-data" without requiring a CDN or build step.
(function () {
  function closestPanel(element) {
    return element.closest("#chat-panel, #upload-response, #job-list") || document;
  }

  function targetFor(element) {
    var selector = element.getAttribute("hx-target");
    if (!selector) return element;
    return document.querySelector(selector) || element;
  }

  function swap(target, html, mode) {
    if (mode === "outerHTML") {
      target.outerHTML = html;
      bind(document);
      return;
    }
    target.innerHTML = html;
    bind(target);
  }

  function formDataFor(element) {
    if (element.tagName === "FORM") {
      return new FormData(element);
    }
    var scope = closestPanel(element);
    var data = new FormData();
    var include = element.getAttribute("hx-include");
    if (include) {
      document.querySelectorAll(include).forEach(function (field) {
        if (field.name) data.append(field.name, field.value);
      });
    }
    scope.querySelectorAll("input, textarea, select").forEach(function (field) {
      if (field.name && field.type !== "file") data.append(field.name, field.value);
    });
    return data;
  }

  function request(element, method, url) {
    var options = {
      method: method,
      headers: { "HX-Request": "true" },
    };
    if (method !== "GET") {
      options.body = formDataFor(element);
    }
    fetch(url, options)
      .then(function (response) { return response.text(); })
      .then(function (html) {
        swap(targetFor(element), html, element.getAttribute("hx-swap") || "innerHTML");
      })
      .catch(function (error) {
        swap(targetFor(element), "<section class=\"response-card\" role=\"alert\"><h3>Request failed</h3><p>" + String(error) + "</p></section>", "innerHTML");
      });
  }

  function parseEvery(trigger) {
    var match = trigger.match(/every\s+(\d+)\s*s/);
    return match ? Number(match[1]) * 1000 : null;
  }

  function bindElement(element) {
    if (element.dataset.htmxLiteBound === "true") return;
    element.dataset.htmxLiteBound = "true";

    var postUrl = element.getAttribute("hx-post");
    var getUrl = element.getAttribute("hx-get");
    var trigger = element.getAttribute("hx-trigger") || "";

    if (postUrl) {
      var eventName = element.tagName === "FORM" ? "submit" : "click";
      element.addEventListener(eventName, function (event) {
        event.preventDefault();
        request(element, "POST", postUrl);
      });
    }

    if (getUrl) {
      if (trigger.indexOf("load") >= 0) {
        window.setTimeout(function () { request(element, "GET", getUrl); }, 1);
      }
      var interval = parseEvery(trigger);
      if (interval) {
        window.setInterval(function () {
          if (document.body.contains(element)) request(element, "GET", getUrl);
        }, interval);
      }
    }
  }

  function bind(root) {
    root.querySelectorAll("[hx-post], [hx-get]").forEach(bindElement);
  }

  document.addEventListener("DOMContentLoaded", function () {
    bind(document);
  });
})();
