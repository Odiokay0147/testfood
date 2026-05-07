const API = window.location.origin;
let token = localStorage.getItem('pg_token')||null;
let currentUser = JSON.parse(localStorage.getItem('pg_user')||'null');
let currentVendor = null;
let cart = {};
let selectedSchedule = 'hourly';
let selectedPayment = 'deposit';
const DEPOSIT_RATES = {hourly:.30,daily:.40,weekly:.50};

window.addEventListener('DOMContentLoaded',()=>{
  if(token && currentUser) showMainApp();
  const d = document.getElementById('deliveryDate');
  if(d){const t=new Date();t.setDate(t.getDate()+1);d.min=t.toISOString().split('T')[0];}
});

function showScreen(id){document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));document.getElementById(id).classList.add('active');window.scrollTo(0,0);}
function navTo(id,btn){showScreen(id);document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');}
function showMainApp(){document.getElementById('bottomNav').style.display='flex';if(currentUser)document.getElementById('avatarBtn').textContent=(currentUser.name||'U')[0].toUpperCase();showScreen('screen-home');loadVendors();}

async function apiFetch(path,opts={}){
  const h={'Content-Type':'application/json'};
  if(token)h['Authorization']=`Bearer ${token}`;
  const r=await fetch(API+path,{...opts,headers:h});
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(d.detail||'Something went wrong');
  return d;
}

function showToast(msg,type=''){const t=document.getElementById('toast');t.textContent=msg;t.className='toast show '+type;setTimeout(()=>t.className='toast',3000);}
function showLoading(v){document.getElementById('loadingOverlay').classList.toggle('show',v);}

async function doSignup(){
  const name=document.getElementById('signup-name').value.trim();
  const email=document.getElementById('signup-email').value.trim();
  const phone=document.getElementById('signup-phone').value.trim();
  const password=document.getElementById('signup-password').value;
  if(!name||!email||!phone||!password)return showToast('Fill all fields','error');
  showLoading(true);
  try{await apiFetch('/signup',{method:'POST',body:JSON.stringify({name,email,phone,password})});showToast('Account created! Login now 🎉','success');showScreen('screen-login');document.getElementById('login-email').value=email;}
  catch(e){showToast(e.message,'error');}
  showLoading(false);
}

async function doLogin(){
  const email=document.getElementById('login-email').value.trim();
  const password=document.getElementById('login-password').value;
  if(!email||!password)return showToast('Enter email and password','error');
  showLoading(true);
  try{const d=await apiFetch('/login',{method:'POST',body:JSON.stringify({email,password})});token=d.access_token;currentUser=d.user;localStorage.setItem('pg_token',token);localStorage.setItem('pg_user',JSON.stringify(currentUser));showToast('Welcome back! 🙌','success');showMainApp();}
  catch(e){showToast(e.message,'error');}
  showLoading(false);
}

function doLogout(){token=null;currentUser=null;localStorage.removeItem('pg_token');localStorage.removeItem('pg_user');document.getElementById('bottomNav').style.display='none';showScreen('screen-login');showToast('You don logout');}

async function loadVendors(){
  try{
    const vendors=await apiFetch('/vendors');
    const colors=['#FF6B35','#2D6A4F'];
    const emojis=['🥘','🍟'];
    document.getElementById('vendorCards').innerHTML=vendors.map((v,i)=>`
      <div class="vendor-card" onclick="openVendor(${v.id},'${esc(v.name)}','${esc(v.description||'')}')">
        <div class="vendor-card-top">
          <div class="vendor-emoji" style="background:${colors[i]}20">${emojis[i]}</div>
          <div class="vendor-info"><h3>${esc(v.name)}</h3><p>${esc(v.description||'Delicious meals available')}</p></div>
        </div>
        <div class="vendor-tags"><span class="vtag">Pre-Order</span><span class="vtag">Deposit Option</span><span class="vtag">WhatsApp Reminder</span></div>
        <div class="vendor-cta">See Menu & Order →</div>
      </div>`).join('');
  }catch(e){showToast('No fit load vendors','error');}
}

async function openVendor(id,name,desc){
  cart={};currentVendor={id,name};
  document.getElementById('menuVendorName').textContent=name;
  updateCartBar();showScreen('screen-menu');
  showLoading(true);
  try{const data=await apiFetch(`/vendors/${id}/menu`);renderMenu(data);}
  catch(e){showToast('No fit load menu','error');}
  showLoading(false);
}

function renderMenu(meals){
  const cats=[...new Set(meals.map(m=>m.category))];
  document.getElementById('categoryTabs').innerHTML=['All',...cats].map((c,i)=>`<div class="cat-tab ${i===0?'active':''}" onclick="filterCat(this,'${c}')">${c}</div>`).join('');
  window._meals=meals;renderMealCards(meals);
}

function filterCat(el,cat){
  document.querySelectorAll('.cat-tab').forEach(t=>t.classList.remove('active'));el.classList.add('active');
  renderMealCards(cat==='All'?window._meals:window._meals.filter(m=>m.category===cat));
}

const EMOJI_MAP={'Rice Dishes':'🍚','Local Favourites':'🍲','Soups & Stews':'🥘','Burgers':'🍔','Sides':'🍟','Chicken':'🍗','Wraps':'🌯','Mains':'🍽️','Healthy':'🥗'};

function renderMealCards(meals){
  document.getElementById('mealList').innerHTML=meals.map(m=>{
    const qty=cart[m.id]?cart[m.id].quantity:0;
    return `<div class="meal-card">
      <div class="meal-emoji">${EMOJI_MAP[m.category]||'🍛'}</div>
      <div class="meal-info"><h4>${esc(m.name)}</h4><p>${esc(m.description||'')}</p><div class="meal-price">GHS ${m.price.toFixed(2)}</div></div>
      <div class="meal-actions">
        <button class="qty-btn" onclick="updateCart(${m.id},${m.price},'${esc(m.name)}',-1)">−</button>
        <span class="qty-count" id="qty-${m.id}">${qty}</span>
        <button class="qty-btn add" onclick="updateCart(${m.id},${m.price},'${esc(m.name)}',1)">+</button>
      </div>
    </div>`;
  }).join('');
}

function updateCart(id,price,name,delta){
  if(!cart[id])cart[id]={meal_id:id,price,name,quantity:0};
  cart[id].quantity=Math.max(0,cart[id].quantity+delta);
  if(cart[id].quantity===0)delete cart[id];
  document.getElementById(`qty-${id}`).textContent=cart[id]?.quantity||0;
  updateCartBar();
}

function updateCartBar(){
  const items=Object.values(cart);
  const total=items.reduce((s,i)=>s+i.price*i.quantity,0);
  const count=items.reduce((s,i)=>s+i.quantity,0);
  const bar=document.getElementById('cartBar');
  if(!count){bar.classList.add('hidden');return;}
  bar.classList.remove('hidden');
  document.getElementById('cartCount').textContent=`${count} item${count>1?'s':''}`;
  document.getElementById('cartTotal').textContent=`GHS ${total.toFixed(2)}`;
}

function getCartTotal(){return Object.values(cart).reduce((s,i)=>s+i.price*i.quantity,0);}

function goToOrder(){
  if(!Object.keys(cart).length)return showToast('Add at least one item first');
  renderOrderSummary();updateDepositInfo();showScreen('screen-order');
}

function renderOrderSummary(){
  const items=Object.values(cart);
  const total=getCartTotal();
  document.getElementById('orderSummaryCard').innerHTML=
    items.map(i=>`<div class="order-item-row"><span>${esc(i.name)} × ${i.quantity}</span><span>GHS ${(i.price*i.quantity).toFixed(2)}</span></div>`).join('')+
    `<div class="order-total-row"><span>Total</span><span style="color:var(--brand)">GHS ${total.toFixed(2)}</span></div>`;
}

function selectSchedule(el,type){
  document.querySelectorAll('.schedule-chip').forEach(c=>c.classList.remove('selected'));
  el.classList.add('selected');selectedSchedule=type;updateDepositInfo();
}

function selectPayment(el,type){
  document.querySelectorAll('.payment-option').forEach(o=>o.classList.remove('selected'));
  el.classList.add('selected');selectedPayment=type;updateDepositInfo();
  document.getElementById('placeOrderBtn').textContent=type==='full'?'Place Order & Pay in Full':'Place Order & Pay Deposit';
}

function updateDepositInfo(){
  const total=getCartTotal();
  const info=document.getElementById('depositInfo');
  if(selectedPayment==='full'){info.style.display='none';return;}
  info.style.display='flex';
  const rate=DEPOSIT_RATES[selectedSchedule];
  document.getElementById('depositInfoText').innerHTML=
    `<strong>You go pay GHS ${(total*rate).toFixed(2)} now (${Math.round(rate*100)}% deposit).</strong> Balance of GHS ${(total*(1-rate)).toFixed(2)} go be due on delivery day. We go WhatsApp remind you.`;
}

async function placeOrder(){
  const date=document.getElementById('deliveryDate').value;
  const time=document.getElementById('deliveryTime').value;
  if(!date)return showToast('Select a delivery date','error');
  if(!time)return showToast('Select a delivery time','error');
  const payload={vendor_id:currentVendor.id,schedule_type:selectedSchedule,delivery_date:date+'T'+time+':00',delivery_time:time,payment_type:selectedPayment,items:Object.values(cart).map(i=>({meal_id:i.meal_id,quantity:i.quantity})),notes:document.getElementById('orderNotes').value||null};
  showLoading(true);
  try{const order=await apiFetch('/orders',{method:'POST',body:JSON.stringify(payload)});showConfirmation(order);}
  catch(e){showToast(e.message,'error');}
  showLoading(false);
}

function showConfirmation(order){
  document.getElementById('confirmRef').textContent=order.order_ref;
  document.getElementById('confirmBreakdown').innerHTML=`
    <div class="confirm-row"><span>Vendor</span><span>${esc(currentVendor.name)}</span></div>
    <div class="confirm-row"><span>Schedule</span><span style="text-transform:capitalize">${order.schedule_type}</span></div>
    <div class="confirm-row"><span>Delivery</span><span>${fmtDate(order.delivery_date)} ${order.delivery_time||''}</span></div>
    <div class="confirm-row"><span>Order Total</span><span>GHS ${order.total_price.toFixed(2)}</span></div>
    <div class="confirm-row highlight"><span>Deposit to Pay</span><span>GHS ${order.deposit_amount.toFixed(2)}</span></div>
    <div class="confirm-row"><span>Balance on Delivery</span><span>GHS ${order.balance_due.toFixed(2)}</span></div>`;
  cart={};updateCartBar();showScreen('screen-confirm');
}

async function loadOrders(){
  const c=document.getElementById('ordersList');
  c.innerHTML='<div style="text-align:center;padding:40px;color:var(--text2)">Loading...</div>';
  try{
    const orders=await apiFetch('/orders/my');
    if(!orders.length){c.innerHTML='<div class="empty-state"><div class="empty-state-icon">📦</div><h3>No orders yet</h3><p>Go choose your food and order now!</p></div>';return;}
    c.innerHTML=orders.map(o=>{
      const needsBal=o.payment_type==='deposit'&&o.deposit_paid&&!o.balance_paid&&o.status==='confirmed';
      return `<div class="order-card">
        <div class="order-card-top"><div class="order-card-ref">${o.order_ref}</div><div class="status-badge status-${o.status}">${o.status}</div></div>
        <div class="order-card-vendor"><strong>${esc(o.vendor_name||'Vendor')}</strong></div>
        <div class="order-card-items">${(o.items||[]).map(i=>`${esc(i.name||'Item')} × ${i.quantity}`).join(', ')||'—'}</div>
        <div class="order-card-footer"><div class="order-card-total">GHS ${o.total_price.toFixed(2)}</div><div class="order-card-date">📅 ${fmtDate(o.delivery_date)}</div></div>
        ${needsBal?`<div class="balance-alert"><div class="balance-alert-text"><strong>Balance due: GHS ${o.balance_due.toFixed(2)}</strong>Pay before dispatch or your order go cancel</div><button class="pay-balance-btn" onclick="payBalance(${o.id},${o.balance_due})">Pay Now</button></div>`:''}
      </div>`;
    }).join('');
  }catch(e){c.innerHTML=`<div class="empty-state"><p>${e.message}</p></div>`;}
}

async function payBalance(orderId,amount){
  showLoading(true);
  try{await apiFetch('/payments',{method:'POST',body:JSON.stringify({order_id:orderId,amount,payment_type:'balance',method:'mobile_money'})});showToast('Balance paid! ✅','success');loadOrders();}
  catch(e){showToast(e.message,'error');}
  showLoading(false);
}

function esc(s){if(!s)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function fmtDate(s){if(!s)return'';try{return new Date(s).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});}catch(e){return s;}}