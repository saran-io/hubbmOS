import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";
import { Badge } from "./Badge";
import { cn } from "../lib/utils";

export interface ImageRecord {
  page: string;
  hubspot_folder: string;
  hubspot_path: string;
  src: string;
  alt: string;
  title: string;
  nearest_heading: string;
}

interface ImageTableProps {
  images: ImageRecord[];
}

const columns: { key: keyof ImageRecord; label: string }[] = [
  { key: "page", label: "Page" },
  { key: "hubspot_folder", label: "HubSpot Folder" },
  { key: "hubspot_path", label: "HubSpot Path" },
  { key: "nearest_heading", label: "Section Heading" },
  { key: "alt", label: "Alt Text" },
];

const rowVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      delay: i * 0.03,
      duration: 0.25,
      ease: "easeOut",
    },
  }),
};

export function ImageTable({ images }: ImageTableProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="relative w-full overflow-auto">
        <table className="w-full min-w-[700px]">
          <thead>
            <tr className="border-b bg-slate-50/80 text-left text-sm font-semibold text-slate-500">
              {columns.map((col) => (
                <th key={col.key} className="p-4">
                  {col.label}
                </th>
              ))}
              <th className="p-4 text-sm font-semibold text-slate-500">Image</th>
            </tr>
          </thead>
          <tbody>
            {images.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="p-6 text-center">
                  No images matched the current filters.
                </td>
              </tr>
            ) : (
              images.map((image, index) => (
                <motion.tr
                  key={`${image.page}-${image.src}-${index}`}
                  custom={index}
                  initial="hidden"
                  animate="visible"
                  variants={rowVariants}
                  className="border-b text-sm text-slate-600 transition-colors hover:bg-slate-50/70"
                >
                  <td className="p-4 font-medium text-slate-900">{image.page}</td>
                  <td className="p-4">
                    <Badge className="bg-slate-900/80 text-white">
                      {image.hubspot_folder || "—"}
                    </Badge>
                  </td>
                  <td className="p-4">
                    <span className="font-mono text-xs text-slate-500">
                      {image.hubspot_path}
                    </span>
                  </td>
                  <td className="p-4">{image.nearest_heading || "—"}</td>
                  <td className="p-4">{image.alt || "—"}</td>
                  <td className="p-4">
                    <a
                      href={image.src}
                      target="_blank"
                      rel="noreferrer"
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600",
                        "transition-colors hover:border-slate-400 hover:text-slate-900"
                      )}
                    >
                      Open
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </td>
                </motion.tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

