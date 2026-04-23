import React from "react";

export default function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="mb-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
      <div>
        {eyebrow && <div className="overline mb-2" data-testid="page-eyebrow">{eyebrow}</div>}
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-slate-900" data-testid="page-title">{title}</h1>
        {subtitle && <p className="text-base text-slate-500 mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}
