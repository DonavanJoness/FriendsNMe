// Frontend-only sharing demo.
// The database team can replace getAccounts() with a real API call later.

const ACCOUNTS_KEY = "friendsnme.accounts";
const SHARED_KEY = "friendsnme.sharedAccounts";

const searchForm = document.getElementById("shareSearchForm");
const searchInput = document.getElementById("shareSearch");
const searchButton = document.getElementById("shareSearchButton");
const statusText = document.getElementById("shareStatus");
const resultsBox = document.getElementById("shareResults");
const sharedBox = document.getElementById("sharedAccounts");

function readJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback;
  } catch {
    return fallback;
  }
}

function saveJSON(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function getAccounts() {
  // Temporary local data. Later this should come from the database.
  return Object.values(readJSON(ACCOUNTS_KEY, {}));
}

function getSharedList() {
  return readJSON(SHARED_KEY, []);
}

function saveSharedList(list) {
  saveJSON(SHARED_KEY, list);
}

function accountMatchesSearch(account, searchText) {
  const username = account.username.toLowerCase();
  const email = account.email.toLowerCase();
  return username.includes(searchText) || email.includes(searchText);
}

function searchAccounts(searchText) {
  const lowerSearch = searchText.toLowerCase();
  return getAccounts().filter((account) => accountMatchesSearch(account, lowerSearch));
}
function addShare(account) {
  const sharedList = getSharedList();
  const alreadyAdded = sharedList.some((person) => person.email === account.email);

  if (!alreadyAdded) {
    sharedList.push(account);
    saveSharedList(sharedList);
  }
}

function removeShare(email) {
  const updatedList = getSharedList().filter((person) => person.email !== email);
  saveSharedList(updatedList);
}

function showResults(accounts) {
  resultsBox.innerHTML = "";

  if (accounts.length === 0) {
    resultsBox.innerHTML = '<p class="empty-share-state">No matching accounts found.</p>';
    return;
  }

  accounts.forEach((account) => {
    const card = document.createElement("article");
    card.className = "share-account-card";
    card.innerHTML = `
      <div>
        <strong>${account.username}</strong>
        <span>${account.email}</span>
      </div>
      <button class="share-add-button" type="button">Add</button>
    `;

    card.querySelector("button").addEventListener("click", () => {
      addShare(account);
      statusText.textContent = "Sharing location with " + account.username + ".";
      showSharedList();
    });

    resultsBox.appendChild(card);
  });
}

function showSharedList() {
  const sharedList = getSharedList();
  sharedBox.innerHTML = "";

  if (sharedList.length === 0) {
    sharedBox.innerHTML = '<p class="empty-share-state">You are not sharing with anyone yet.</p>';
    return;
  }

  sharedList.forEach((account) => {
    const row = document.createElement("article");
    row.className = "shared-account-row";
    row.innerHTML = `
      <div>
        <strong>${account.username}</strong>
        <span>${account.email}</span>
      </div>
      <button class="share-remove-button" type="button">Remove</button>
    `;

    row.querySelector("button").addEventListener("click", () => {
      removeShare(account.email);
      statusText.textContent = "Stopped sharing with " + account.username + ".";
      showSharedList();
    });

    sharedBox.appendChild(row);
  });
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

  const matches = searchAccounts(searchText);
  showResults(matches);
  statusText.textContent = matches.length
    ? "Choose an account to share with."
    : "No accounts found yet.";
});

showSharedList();

