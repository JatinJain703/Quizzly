import { FC, useState, useRef, useEffect } from 'react';

type TopicItem = {
  id: string;
  name: string;
  source_filename: string;
};

type MainCanvasProps = {
  topics: TopicItem[];
};

export const MainCanvas: FC<MainCanvasProps> = ({ topics }) => {
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [topicError, setTopicError] = useState<string>('');
  const [difficulty, setDifficulty] = useState<string>('medium');
  const [quantity, setQuantity] = useState<number | string>(0);
  const [quantityError, setQuantityError] = useState<string>('');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleGenerate = async () => {
    if (selectedTopics.length === 0) {
      setTopicError("Please select at least one topic.");
      return;
    }
    
    if (quantity === '' || Number(quantity) <= 0) {
      setQuantityError("Please update quantity to be greater than 0.");
      return;
    }
    
    setIsGenerating(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          topics: selectedTopics,
          difficulty: difficulty,
          count: Number(quantity)
        })
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Generated questions:", data);
        alert("Generated successfully! Check console for output.");
      } else {
        const errorText = await response.text();
        console.error("Failed to generate:", errorText);
        alert("Failed to generate questions. See console.");
      }
    } catch (e) {
      console.error("Error during generation:", e);
      alert("Error during generation. See console.");
    } finally {
      setIsGenerating(false);
    }
  };

  const toggleTopic = (name: string) => {
    setSelectedTopics(prev => {
      const newTopics = prev.includes(name) ? prev.filter(t => t !== name) : [...prev, name];
      if (newTopics.length > 0) setTopicError('');
      return newTopics;
    });
  };

  return (
    <main className="flex-1 overflow-y-auto p-margin-mobile md:p-margin-desktop bg-surface relative z-0">
      <div className="max-w-[800px] mx-auto w-full h-full flex flex-col justify-center">
        <div className="mb-stack-xl">
          <h1 className="font-display text-headline-lg-mobile md:text-headline-lg font-bold mb-4">GENERATE ASSESSMENT</h1>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl">
            Configure the parameters for the multi-agent generation process. The system will synthesize information from the selected corpus to create highly specific evaluation materials.
          </p>
        </div>
        <div className="border border-primary bg-white p-stack-lg space-y-stack-lg shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
          
          {/* Topic Field */}
          <div className="flex flex-col gap-2 relative" ref={dropdownRef}>
            <label className="font-label-md text-label-md uppercase tracking-wider text-primary flex items-center" htmlFor="topic">
              Topic<span className="material-symbols-outlined text-[18px] ml-auto align-middle" style={{ fontVariationSettings: "'FILL' 0" }}>search</span>
            </label>
            
            <div 
              className={`w-full border-b border-t-0 border-l-0 border-r-0 bg-transparent px-0 py-2 font-body-md text-body-md text-primary cursor-pointer min-h-[40px] flex flex-wrap gap-2 items-center ${topicError ? 'border-error' : 'border-primary'}`}
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            >
              {selectedTopics.length === 0 ? (
                <span className="text-on-surface-variant/50">Select topics...</span>
              ) : (
                selectedTopics.map(t => (
                  <span key={t} className="bg-primary text-on-primary px-2 py-1 text-xs flex items-center gap-1">
                    {t}
                    <span 
                      className="material-symbols-outlined text-[14px] cursor-pointer hover:text-error" 
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleTopic(t);
                      }}
                      style={{ fontVariationSettings: "'FILL' 0" }}
                    >
                      close
                    </span>
                  </span>
                ))
              )}
            </div>
            
            {/* Dropdown Menu */}
            {isDropdownOpen && (
              <div className="absolute top-full left-0 w-full mt-1 bg-white border border-primary shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] max-h-60 overflow-y-auto z-10">
                {topics.length === 0 ? (
                  <div className="p-3 text-on-surface-variant text-sm font-body-md">No topics found. Ingest some documents first.</div>
                ) : (
                  topics.map((t) => {
                    const isSelected = selectedTopics.includes(t.name);
                    return (
                      <div 
                        key={t.id} 
                        className={`p-2 hover:bg-secondary-container cursor-pointer border-b border-surface-variant last:border-0 text-sm flex items-center justify-between ${isSelected ? 'bg-surface font-semibold text-primary' : 'text-on-surface-variant'}`}
                        onClick={() => toggleTopic(t.name)}
                      >
                        <div>
                          <div>{t.name}</div>
                          <div className="text-[10px] opacity-75 mt-0.5">Source: {t.source_filename}</div>
                        </div>
                        {isSelected && (
                          <span className="material-symbols-outlined text-[18px] text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>check</span>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
            {topicError && (
              <div className="text-error text-xs font-body-md absolute -bottom-5 left-0">{topicError}</div>
            )}
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-stack-lg">
            {/* Complexity Field */}
            <div className="flex flex-col gap-2">
              <label className="font-label-md text-label-md uppercase tracking-wider text-primary" htmlFor="complexity">Complexity</label>
              <select 
                className="w-full border border-primary bg-white px-3 py-2 focus:ring-0 focus:border-primary font-body-md text-body-md text-primary outline-none cursor-pointer rounded-none" 
                id="complexity" 
                name="complexity"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
            {/* Quantity Field */}
            <div className="flex flex-col gap-2 relative">
              <label className="font-label-md text-label-md uppercase tracking-wider text-primary" htmlFor="quantity">Quantity</label>
              <input 
                className={`w-full border bg-white px-3 py-2 focus:ring-0 font-body-md text-body-md text-primary rounded-none outline-none ${quantityError ? 'border-error focus:border-error' : 'border-primary focus:border-primary'}`} 
                id="quantity" 
                max="50" 
                min="0" 
                name="quantity" 
                type="number" 
                value={quantity}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === '') {
                    setQuantity('');
                  } else {
                    const num = parseInt(val, 10);
                    setQuantity(num);
                    if (num > 0) {
                      setQuantityError('');
                    }
                  }
                }}
              />
              {quantityError && (
                <div className="text-error text-xs font-body-md">{quantityError}</div>
              )}
            </div>
          </div>
          
          <div className="pt-stack-md mt-stack-md border-t border-primary">
            <button 
              onClick={handleGenerate}
              disabled={isGenerating}
              className="w-full bg-primary text-on-primary hover:bg-surface hover:text-primary border-2 border-primary transition-colors duration-200 py-4 font-label-md text-label-md uppercase tracking-widest flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isGenerating ? (
                <>
                  <span className="material-symbols-outlined animate-spin" style={{ fontVariationSettings: "'FILL' 1" }}>sync</span>
                  <span>Generating...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>model_training</span>
                  <span>Initialize generation</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
};
