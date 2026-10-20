export default function ExamplePanel({title='Try this example',example,hint,onUse,disabled=false}:{title?:string;example:string;hint:string;onUse?:()=>void;disabled?:boolean}){
 return <aside className="guide-panel example-panel" aria-label={title}><p className="eyebrow">EXAMPLE INPUT</p><h2>{title}</h2><pre className="example-copy">{example}</pre><p>{hint}</p>{onUse&&<button type="button" className="secondary" disabled={disabled} onClick={onUse}>Use example</button>}</aside>;
}
