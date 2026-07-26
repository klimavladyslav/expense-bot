const SHEET_NAME = "Containers";

const HEADERS = [
  "Invoice No",
  "Invoice Date",
  "Supplier",
  "Category",
  "Product",
  "Qty",
  "CBM",
  "Unit",
  "Unit Price",
  "Invoice Amount",
  "Currency",
  "Customs",
  "Delivery",
  "Transaction",
  "Total Unit Cost",
  "Split by",
  "Parsed At"
];

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName(SHEET_NAME);

    if (!sheet) {
      sheet = ss.insertSheet(SHEET_NAME);
    }

    // Ensure header row exists
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);
      // Style header
      const headerRange = sheet.getRange(1, 1, 1, HEADERS.length);
      headerRange.setFontWeight("bold");
      headerRange.setBackground("#4a86e8");
      headerRange.setFontColor("#ffffff");
    }

    // Append all rows
    const rows = data.rows || [];
    for (const row of rows) {
      sheet.appendRow(row);
    }

    // Auto-resize columns
    sheet.autoResizeColumns(1, HEADERS.length);

    return ContentService.createTextOutput(
      JSON.stringify({ success: true, rows_added: rows.length })
    ).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ success: false, error: err.toString() })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput("Containers webhook active ✓");
}
