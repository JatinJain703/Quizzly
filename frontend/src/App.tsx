import { useEffect, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { MainCanvas } from './components/MainCanvas';

type FileInfo = {
  name: string;
  source_type: string;
  chunks: number;
};

const API_BASE = 'http://127.0.0.1:8000';

function App() {
  const [textbooks, setTextbooks] = useState<FileInfo[]>([]);
  const [examPapers, setExamPapers] = useState<FileInfo[]>([]);
  const [topics, setTopics] = useState<any[]>([]);

  const fetchData = async () => {
    try {
      // Fetch files
      const filesRes = await fetch(`${API_BASE}/files`);
      if (filesRes.ok) {
        const data = await filesRes.json();
        setTextbooks(data.textbooks || []);
        setExamPapers(data.exam_papers || []);
      }

      // Fetch topics
      const topicsRes = await fetch(`${API_BASE}/topics`);
      if (topicsRes.ok) {
        const data = await topicsRes.json();
        setTopics(data.topics || []);
      }
    } catch (e) {
      console.error('Error fetching data:', e);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleUpload = async (file: File, sourceType: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('source_type', sourceType);

    try {
      const response = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        // Re-fetch files to update the list
        await fetchData();
      } else {
        console.error('Failed to ingest file:', await response.text());
        alert('Failed to ingest file. See console for details.');
      }
    } catch (e) {
      console.error('Error uploading file:', e);
      alert('Error uploading file.');
    }
  };

  return (
    <div className="bg-surface text-on-surface h-screen flex flex-col antialiased">
      {/* TopAppBar */}
      <header className="bg-surface dark:bg-surface text-primary dark:text-on-surface font-display text-headline-md font-bold uppercase docked full-width top-0 border-b border-primary dark:border-on-surface flat no-shadows flex justify-between items-center w-full px-margin-desktop py-stack-md z-10 bg-white">
        <div className="font-display text-headline-md font-extrabold text-primary dark:text-on-surface tracking-tighter flex items-center">
          <img src="https://lh3.googleusercontent.com/aida/AP1WRLtBBtxhcj846yz6kuJHxBINLuIeALZosYa1kNQp_qywfcjj50ZyPU24Kr9beMGL9IB8QjzfA09PtCbTpEX9g_3ZdDd3usPYBS2MnBF6UMZm8jj9hDS2RNSvj6t1kYDmiy4mn0E9hHOAagpdKjytseWWRMswahc8f7Do7zHWDupL-E9CSuYXtKkzyYuZyhpbeld2M1wgZQXWgpcHw8fn7IC1YuJs2RdDovQBFb1a3lQy3uzIfVvxx3Sn12w" className="w-8 h-8 mr-2" alt="Quizzly Logo" />
          QUIZZLY
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar 
          textbooks={textbooks} 
          examPapers={examPapers} 
          onUpload={handleUpload} 
        />
        <MainCanvas topics={topics} />
      </div>
    </div>
  );
}

export default App;
