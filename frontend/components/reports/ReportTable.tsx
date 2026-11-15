"use client";

import Link from "next/link";
import { useState } from "react";
import Icon, { type IconName } from "@/components/Icon";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { IconButton } from "@/components/ui/icon-button";

export type ReportCell = { content: React.ReactNode; href?: string; tone?: "danger" | "success" | "muted" };
export type ReportRow = { key: string; label: React.ReactNode; labelHref?: string; cells: ReportCell[] };

const toneClass = (cell?: ReportCell) => (cell?.tone ? ` report-${cell.tone}` : "");
const renderCell = (cell?: ReportCell) => (cell?.href ? <Link href={cell.href}>{cell.content}</Link> : cell?.content);

// Report table with an icon toggle that swaps rows and columns, so wide breakdowns can also be read top to bottom.
export default function ReportTable({ title, subtitle, nameHeader = "Name", description, icon, action, headers, rows, totals, loading, empty }: {
  title: string; subtitle?: string; nameHeader?: string; description?: string; icon: IconName; action?: React.ReactNode; headers: string[]; rows: ReportRow[]; totals?: React.ReactNode[]; loading?: boolean; empty: string;
}) {
  const [flipped, setFlipped] = useState(false);
  const label = (row: ReportRow) => row.labelHref ? <Link href={row.labelHref}>{row.label}</Link> : row.label;
  return <Card className="report-card">
    <CardHeader><CardTitle><Icon name={icon} size={18} /> {title}{subtitle && <span className="report-subtitle">{subtitle}</span>}</CardTitle>{description && <CardDescription>{description}</CardDescription>}
      <CardAction><div className="report-actions">{action}{rows.length > 0 && <IconButton label={flipped ? "Show users as rows" : "Switch rows and columns"} aria-pressed={flipped} onClick={() => setFlipped(value => !value)}><Icon name="swap" /></IconButton>}</div></CardAction></CardHeader>
    <CardContent>
      {loading ? <div className="report-skeleton">{Array.from({ length: 4 }, (_, index) => <span key={index} className="skeleton" />)}</div>
        : !rows.length ? <div className="report-empty"><Icon name="chart" size={28} /><strong>No records yet</strong><span className="small muted">{empty}</span></div>
          : <div className="report-scroll">{flipped
            ? <table className="report-table">
              <thead><tr><th>Metric</th>{rows.map(row => <th key={row.key} className="cell-right">{label(row)}</th>)}{totals && <th className="cell-right">Total</th>}</tr></thead>
              <tbody>{headers.map((header, index) => <tr key={header}>
                <th scope="row">{header}</th>
                {rows.map(row => <td key={row.key} className={`cell-right${toneClass(row.cells[index])}`}>{renderCell(row.cells[index])}</td>)}
                {totals && <td className="cell-right report-total">{totals[index]}</td>}
              </tr>)}</tbody>
            </table>
            : <table className="report-table">
              <thead><tr><th>{nameHeader}</th>{headers.map(header => <th key={header} className="cell-right">{header}</th>)}</tr></thead>
              <tbody>{rows.map(row => <tr key={row.key}>
                <th scope="row">{label(row)}</th>
                {row.cells.map((cell, index) => <td key={index} className={`cell-right${toneClass(cell)}`}>{renderCell(cell)}</td>)}
              </tr>)}</tbody>
              {totals && <tfoot><tr><th scope="row">Total</th>{totals.map((value, index) => <td key={index} className="cell-right">{value}</td>)}</tr></tfoot>}
            </table>}</div>}
    </CardContent>
  </Card>;
}
