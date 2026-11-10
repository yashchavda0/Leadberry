"use client";

import Icon from "@/components/Icon";
import { Dialog as UiDialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { IconButton } from "@/components/ui/icon-button";

export default function Dialog({ title, subtitle, logo, closeLabel, wide, fixed, actions, onClose, children }: {
  title: string; subtitle: string; logo?: React.ReactNode; closeLabel: string; wide?: boolean; fixed?: boolean; actions?: React.ReactNode; onClose: () => void; children: React.ReactNode;
}) {
  return <UiDialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent size={wide ? "lg" : "md"} className={fixed ? "ui-dialog-fixed" : undefined} hideClose>
      <div className="marketplace-dialog-header">
        <div className="marketplace-title">{logo}<div><DialogTitle>{title}</DialogTitle><DialogDescription>{subtitle}</DialogDescription></div></div>
        <div className="dialog-actions">{actions}<IconButton label={closeLabel} onClick={onClose}><Icon name="close" /></IconButton></div>
      </div>
      {children}
    </DialogContent>
  </UiDialog>;
}
