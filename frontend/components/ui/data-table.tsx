"use client";

import * as React from "react";
import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table";
import Icon from "@/components/Icon";
import ScrollArea from "@/components/ScrollArea";
import { Pagination, type PagerList } from "@/components/Ui";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> { align?: "left" | "center" | "right"; width?: string }
}

const cellClass = (align?: "left" | "center" | "right") => align === "right" ? "cell-right" : align === "center" ? "cell-center" : undefined;

// TanStack-powered table: sortable headers on the current page, skeleton while loading, shared pager. Mark a column sortable with `enableSorting`.
export function DataTable<T>({ columns, data, rowKey, empty, list, skeletonRows = 6 }: {
  columns: ColumnDef<T, unknown>[]; data: T[] | null | undefined; rowKey: (row: T) => string; empty?: React.ReactNode; list?: PagerList; skeletonRows?: number;
}) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const table = useReactTable({
    data: data ?? [], columns, state: { sorting }, onSortingChange: setSorting,
    getRowId: row => rowKey(row), getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), enableSortingRemoval: true,
  });
  const loading = data == null;
  return <div className="card data-table">
    {!loading && !data.length ? (empty ?? <div className="empty-state"><h3>Nothing to show</h3></div>) : <ScrollArea direction="x" label="Table"><table className="ui-table">
      <colgroup>{table.getVisibleLeafColumns().map(column => <col key={column.id} style={{ width: column.columnDef.meta?.width }} />)}</colgroup>
      <thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => {
        const sorted = header.column.getIsSorted();
        return <th key={header.id} className={cellClass(header.column.columnDef.meta?.align)} aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}>
          {header.column.getCanSort()
            ? <button type="button" className="ui-sort" onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}<span className={`ui-sort-icon${sorted ? " on" : ""}`}><Icon name="chevron" size={12} /></span></button>
            : flexRender(header.column.columnDef.header, header.getContext())}
        </th>;
      })}</tr>)}</thead>
      <tbody>{loading
        ? Array.from({ length: skeletonRows }, (_, index) => <tr key={index} className="skeleton-row" aria-hidden="true">{columns.map((_, cell) => <td key={cell}><span className="skeleton" /></td>)}</tr>)
        : table.getRowModel().rows.map(row => <tr key={row.id}>{row.getVisibleCells().map(cell => <td key={cell.id} className={cellClass(cell.column.columnDef.meta?.align)}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}
      </tbody>
    </table></ScrollArea>}
    {list && <Pagination list={list} />}
  </div>;
}
