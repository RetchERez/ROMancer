import {heading} from '../common.js';
import {renderHub} from '../tutorial.js';
export async function render(ctx){ctx.state.tutorialData=await ctx.api.call('tutorial.get');return heading('','Tutorials','')+renderHub(ctx.state.tutorialData);}
