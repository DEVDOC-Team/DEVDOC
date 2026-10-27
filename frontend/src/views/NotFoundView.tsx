import React from 'react';
import { Panel } from '../components/ui/Panel';
import { Button } from '../components/ui/Button';
import { Compass, ArrowLeft } from 'lucide-react';

interface NotFoundViewProps {
  onNavigate: (view: string) => void;
}

export const NotFoundView: React.FC<NotFoundViewProps> = ({ onNavigate }) => {
  return (
    <div className="view-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Panel style={{ maxWidth: '480px', textAlign: 'center', padding: '32px 24px' }}>
        <div style={{ display: 'inline-flex', padding: '14px', background: 'rgba(174, 184, 192, 0.1)', borderRadius: '50%', color: 'var(--devdoc-accent)', marginBottom: '14px' }}>
          <Compass size={32} />
        </div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
          404 · Uncharted Route
        </h2>
        <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '8px', lineHeight: 1.5 }}>
          The requested DevOps console segment does not exist or has been migrated. Return to the active investigation or operational deck.
        </p>
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', marginTop: '20px' }}>
          <Button variant="secondary" size="sm" onClick={() => onNavigate('overview')} icon={<ArrowLeft size={14} />}>
            Overview Deck
          </Button>
          <Button variant="primary" size="sm" onClick={() => onNavigate('investigations')}>
            Active Investigation
          </Button>
        </div>
      </Panel>
    </div>
  );
};
