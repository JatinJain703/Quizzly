import { useRef, useState, ChangeEvent, FC } from 'react';

type FileInfo = {
  name: string;
  source_type: string;
  chunks: number;
};

type SidebarProps = {
  textbooks: FileInfo[];
  examPapers: FileInfo[];
  onUpload: (file: File, sourceType: string) => Promise<void>;
};

export const Sidebar: FC<SidebarProps> = ({ textbooks, examPapers, onUpload }) => {
  const [ingestingType, setIngestingType] = useState<string | null>(null);
  const textbookInputRef = useRef<HTMLInputElement>(null);
  const examPaperInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>, type: string) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    setIngestingType(type);
    try {
      await onUpload(file, type);
    } finally {
      setIngestingType(null);
      // Reset input
      event.target.value = '';
    }
  };

  return (
    <nav className="hidden md:flex bg-surface text-primary font-label-md text-label-md uppercase tracking-widest border-r border-primary flat no-shadows flex-col h-full w-64 pt-stack-md pb-stack-xl bg-white shrink-0 overflow-y-auto z-0 relative">
      <div className="px-stack-md mb-stack-lg">
        <div className="font-display text-headline-md font-black">LIBRARY</div>
        <div className="text-on-surface-variant font-label-sm text-label-sm mt-1">MANAGE DOCUMENTS</div>
      </div>

      {/* Textbooks Section */}
      <div className="mb-stack-lg">
        <div className="px-stack-md py-stack-sm text-on-surface-variant flex items-center gap-2 justify-between group">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 0" }}>book</span>
            <span>Textbooks /{textbooks.length}</span>
          </div>
          <button 
            onClick={() => textbookInputRef.current?.click()}
            disabled={ingestingType !== null}
            className="ml-auto hover:bg-primary hover:text-on-primary rounded-none p-1 transition-colors duration-150 flex items-center justify-center disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: "'FILL' 0" }}>add</span>
          </button>
          <input 
            type="file" 
            ref={textbookInputRef} 
            accept="application/pdf" 
            className="hidden" 
            onChange={(e) => handleFileChange(e, 'textbook')} 
          />
        </div>
        <div className="flex flex-col pl-stack-xl pr-stack-md mt-2 space-y-2">
          {ingestingType === 'textbook' && (
            <div className="text-primary px-2 py-1 flex items-center gap-2 text-xs border border-transparent truncate">
              <span className="material-symbols-outlined text-[16px] animate-spin">sync</span>
              <span className="truncate">Ingesting...</span>
            </div>
          )}
          {textbooks.slice(0, 4).map((file, idx) => (
            <div key={idx} title={file.name} className="text-primary hover:bg-secondary-container px-2 py-1 flex items-center gap-2 text-xs border border-transparent transition-colors duration-150 truncate cursor-pointer">
              <span className="material-symbols-outlined text-[16px]" style={{ fontVariationSettings: "'FILL' 0" }}>description</span>
              <span className="truncate">{file.name}</span>
            </div>
          ))}
          {textbooks.length > 4 && (
            <div className="text-on-surface-variant px-2 py-1 text-xs">+{textbooks.length - 4} more</div>
          )}
        </div>
      </div>

      {/* Exam Papers Section */}
      <div className="mb-stack-lg">
        <div className="px-stack-md py-stack-sm text-primary flex items-center gap-2 justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 0" }}>book</span>
            <span>EXAM PAPERS /{examPapers.length}</span>
          </div>
          <button 
            onClick={() => examPaperInputRef.current?.click()}
            disabled={ingestingType !== null}
            className="ml-auto hover:bg-primary hover:text-on-primary rounded-none p-1 transition-colors duration-150 flex items-center justify-center disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: "'FILL' 0" }}>add</span>
          </button>
          <input 
            type="file" 
            ref={examPaperInputRef} 
            accept="application/pdf" 
            className="hidden" 
            onChange={(e) => handleFileChange(e, 'exam_paper')} 
          />
        </div>
        <div className="flex flex-col pl-stack-xl pr-stack-md mt-2 space-y-2">
          {ingestingType === 'exam_paper' && (
            <div className="text-primary px-2 py-1 flex items-center gap-2 text-xs border border-transparent truncate">
              <span className="material-symbols-outlined text-[16px] animate-spin">sync</span>
              <span className="truncate">Ingesting...</span>
            </div>
          )}
          {examPapers.slice(0, 4).map((file, idx) => (
            <div key={idx} title={file.name} className="text-primary hover:bg-secondary-container px-2 py-1 flex items-center gap-2 text-xs border border-transparent transition-colors duration-150 truncate cursor-pointer">
              <span className="material-symbols-outlined text-[16px]" style={{ fontVariationSettings: "'FILL' 0" }}>description</span>
              <span className="truncate">{file.name}</span>
            </div>
          ))}
          {examPapers.length > 4 && (
            <div className="text-on-surface-variant px-2 py-1 text-xs">+{examPapers.length - 4} more</div>
          )}
        </div>
      </div>
    </nav>
  );
};
