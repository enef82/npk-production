"use client";

import ExcelJS from "exceljs";

export type ExcelColumn = { key: string; label: string; width?: number };

export async function exportRowsToExcel(
  fileName: string,
  columns: ExcelColumn[],
  rows: Record<string, string | number | null>[],
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("Данные");
  sheet.columns = columns.map((column) => ({
    header: column.label,
    key: column.key,
    width: column.width ?? 24,
  }));
  sheet.getRow(1).font = { bold: true };
  rows.forEach((row) => sheet.addRow(row));

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName.endsWith(".xlsx") ? fileName : `${fileName}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
