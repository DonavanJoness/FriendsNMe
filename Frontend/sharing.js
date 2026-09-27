// Location sharing: choose who can see your location on their map.
// Sharing is one-way. Adding someone lets them see you; you see them
// only if they add you too.

const searchForm = document.getElementById("shareSearchForm");
const searchInput = document.getElementById("shareSearch");
const searchButton = document.getElementById("shareSearchButton");
const statusText = document.getElementById("shareStatus");
const resultsBox = document.getElementById("shareResults");
const sharedBox = document.getElementById("sharedAccounts");

let lastResults = [];

// JSON request to the Flask API; the session cookie comes along.
async function api(path, { method = "GET", body } = {}) {
  const options = { method, credentials: "same-origin" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Could not reach the server. Is Flask running?");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Server returned HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function showError(error) {
  if (error.status === 401) {
    statusText.textContent = "Sign in on the Home page to manage sharing.";
    searchInput.disabled = true;
    searchButton.disabled = true;
    return;
  }
  statusText.textContent = error.message;
}

// Build elements with textContent, never innerHTML, so a username
// like "<img onerror=...>" is shown as text instead of running.
function emptyState(text) {
  const empty = document.createElement("p");
  empty.className = "empty-share-state";
  empty.textContent = text;
  return empty;
}

function accountCard(account, detail, cardClass, button) {
  const card = document.createElement("article");
  card.className = cardClass;

  const text = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = account.username;
  const info = document.createElement("span");
  info.textContent = detail;
  text.append(name, info);

  card.append(text, button);
  return card;
}

function makeButton(className, label, onClick) {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function showResults(accounts) {
  lastResults = accounts;
  resultsBox.replaceChildren();

  if (accounts.length === 0) {
    resultsBox.appendChild(emptyState("No matching accounts found."));
    return;
  }

  accounts.forEach((account) => {
    const button = makeButton("share-add-button", account.sharing ? "Sharing" : "Share", () => {
      button.disabled = true;
      api("/api/shares", { method: "POST", body: { userId: account.id } })
        .then(() => {
          account.sharing = true;
          statusText.textContent = `${account.username} can now see your location.`;
          showResults(lastResults);
          loadSharedList();
        })
        .catch((error) => {
          button.disabled = false;
          showError(error);
        });
    });
    button.disabled = account.sharing;

    const detail = account.sharing ? "Can see your location" : "Can't see your location";
    resultsBox.appendChild(accountCard(account, detail, "share-account-card", button));
  });
}

function showSharedList(accounts) {
  sharedBox.replaceChildren();

  if (accounts.length === 0) {
    sharedBox.appendChild(emptyState("You are not sharing with anyone yet."));
    return;
  }

  accounts.forEach((account) => {
    const button = makeButton("share-remove-button", "Stop sharing", () => {
      button.disabled = true;
      api(`/api/shares/${encodeURIComponent(account.id)}`, { method: "DELETE" })
        .then(() => {
          statusText.textContent = `Stopped sharing with ${account.username}.`;
          const result = lastResults.find((match) => match.id === account.id);
          if (result) {
            result.sharing = false;
            showResults(lastResults);
          }
          loadSharedList();
        })
        .catch((error) => {
          button.disabled = false;
          showError(error);
        });
    });

    sharedBox.appendChild(
      accountCard(account, "Can see your location", "shared-account-row", button)
    );
  });
}

function loadSharedList() {
  api("/api/shares")
    .then((data) => showSharedList(data.sharingWith))
    .catch(showError);
}

searchInput.addEventListener("input", () => {
  searchButton.disabled = searchInput.value.trim().length < 2;
});

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const searchText = searchInput.value.trim();
  if (searchText.length < 2) {
    statusText.textContent = "Type at least 2 characters to search.";
    return;
  }

  api(`/api/users/search?q=${encodeURIComponent(searchText)}`)
    .then((data) => {
      showResults(data.users);
      statusText.textContent = data.users.length
        ? "Choose who can see your location."
        : "No accounts found. Emails must match exactly.";
    })
    .catch(showError);
});

loadSharedList();
