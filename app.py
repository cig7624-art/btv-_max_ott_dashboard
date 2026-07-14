const scanButton = document.getElementById("scanButton");
const result = document.getElementById("result");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

async function getActiveTab() {
  const tabs = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  return tabs[0];
}

scanButton.addEventListener("click", async () => {
  result.textContent = "현재 화면을 읽는 중입니다...";
  statusText.textContent = "연결 확인 중";
  statusDot.classList.remove("connected");

  try {
    const tab = await getActiveTab();

    if (!tab || !tab.id) {
      throw new Error("현재 탭을 찾을 수 없습니다.");
    }

    const response = await chrome.tabs.sendMessage(tab.id, {
      type: "SCAN_CURRENT_PAGE"
    });

    if (!response) {
      throw new Error("페이지에서 응답을 받지 못했습니다.");
    }

    statusDot.classList.add("connected");
    statusText.textContent = "B tv+ 화면 연결됨";

    result.textContent = [
      `페이지 제목: ${response.pageTitle || "-"}`,
      `현재 주소: ${response.url || "-"}`,
      "",
      "화면 텍스트 일부",
      "--------------------",
      response.text || "읽을 수 있는 텍스트가 없습니다."
    ].join("\n");
  } catch (error) {
    statusText.textContent = "연결 실패";
    result.textContent = [
      "화면을 읽지 못했습니다.",
      "",
      error.message,
      "",
      "B tv+ 웹 화면을 연 뒤 다시 시도하세요."
    ].join("\n");
  }
});
