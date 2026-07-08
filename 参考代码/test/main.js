// username
function P_Username(username) {
    if (username===''){
        return {valid:false,message:'用户名不能为空'};
    }
    if ((username.length<4)||(username.length>16)||(!(/^[a-zA-Z0-9_]+$/.test(username)))) {
        return {valid:false,message:'4-16位，字母开头，仅字母数字下划线'}
    }
    return {valid:true,message:'用户名格式正确'};
};

const inp1=document.querySelector('#username');
const tip1=document.querySelector('#tipUsername');
inp1.addEventListener('input',function(){
    let res=P_Username(inp1.value);
    tip1.innerText=res.message;
    tip1.className=res.valid?'tip success':'tip error';
    inp1.className=res.valid?'success-border':'error-border';
});

//password
function P_Password(password) {
    if (password===''){
        return {valid:false,message:'密码不能为空'};
    }
    if (password.length<8){
        return {valid:false,message:'密码长度不能小于8位'};
    }
    if (!(/^(?=.*[0-9])(?=.*[a-zA-Z])(?=.*[!@#$%^&*])[a-zA-Z0-9!@#$%^&*]+$/.test(password))){
        return {valid:false,message:'密码必须包含数字和字母和特殊字符'};
    }
    return {valid:true,message:'密码格式正确'};
};

function P_Password_level(password){
    if (password === '') {
        strengthFill.style.width = '0';
        strengthFill.className = 'password-bar-fill';
        tip2.innerText = '';
        return;
    }
    let level = 0;
    if (/[a-z]/.test(password)) level++;      
    if (/[A-Z]/.test(password)) level++;      
    if (/[0-9]/.test(password)) level++;   
    if (/[!@#$%^&*]/.test(password)) level++;
    if (password.length >= 8) level++;       

    if (level <= 2) {
        strengthFill.style.width = '33%';
        strengthFill.className = 'password-bar-fill strength-weak';
    } else if (level === 3 || level === 4) {
        strengthFill.style.width = '66%';
        strengthFill.className = 'password-bar-fill strength-medium';
    } else {
        strengthFill.style.width = '100%';
        strengthFill.className = 'password-bar-fill strength-strong';
    }
}

const inp2=document.querySelector('#password');
const tip2=document.querySelector('#tipPassword');
const strengthFill=document.querySelector('.password-bar-fill');
document.querySelector('.toggle-pwd').addEventListener('click',function(){
    const isPassword = inp2.type === 'password';
    inp2.type = isPassword ? 'text' : 'password';
    this.innerText = isPassword ? '隐藏' : '显示';
});
inp2.addEventListener('input',function(){
    P_Password_level(inp2.value);
    let res=P_Password(inp2.value);
    tip2.innerText=res.message;
    tip2.className=res.valid?'tip success':'tip error';
    inp2.className=res.valid?'success-border':'error-border';
});

//password2
function P_Password2(password2) {
    if ((password2===inp2.value)&&!(password2==='')){
        return {valid:true,message:'密码一致'};
    }
    return {valid:false,message:'密码不一致'};
};

const inp3=document.querySelector('#password2');
const tip3=document.querySelector('#tipPassword2');
document.querySelector('.toggle-pwd-confirm').addEventListener('click',function(){
    const isPassword = inp3.type === 'password';
    inp3.type = isPassword ? 'text' : 'password';
    this.innerText = isPassword ? '隐藏' : '显示';
});
inp3.addEventListener('input',function(){
    let res=P_Password2(inp3.value);
    tip3.innerText=res.message;
    tip3.className=res.valid?'tip success':'tip error';
    inp3.className=res.valid?'success-border':'error-border';
});

//email
function P_Email(email) {
    if (email===''){
        return {valid:false,message:'邮箱不能为空'};
    }
    if (!(/^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$/.test(email))){
        return {valid:false,message:'邮箱格式不正确'};
    }
    return {valid:true,message:'邮箱格式正确'};
};

const inp4=document.querySelector('#email');
const tip4=document.querySelector('#tipEmail');
inp4.addEventListener('input',function(){
    let res=P_Email(inp4.value);
    tip4.innerText=res.message;
    tip4.className=res.valid?'tip success':'tip error';
    inp4.className=res.valid?'success-border':'error-border';
});

//phone
function P_Phone(phone) {
    if (phone===''){
        return {valid:false,message:'手机号不能为空'};
    }
    if (!(/^1[3-9]\d{9}$/.test(phone)) || (phone.length!=11)){
        return {valid:false,message:'手机号格式不正确'};
    }
    return {valid:true,message:'手机号格式正确'};
};

const inp5=document.querySelector('#phone');
const tip5=document.querySelector('#tipPhone');
inp5.addEventListener('input',function(){
    let res=P_Phone(inp5.value);
    tip5.innerText=res.message;
    tip5.className=res.valid?'tip success':'tip error';
    inp5.className=res.valid?'success-border':'error-border';
});


const form = document.querySelector('#registerForm');
form.addEventListener('submit', function (e) {
  e.preventDefault();

  const uRes = P_Username(inp1.value);
  tip1.innerText = uRes.message;
  tip1.className = uRes.valid ? 'tip success' : 'tip error';
  inp1.className = uRes.valid ? 'success-border' : 'error-border';

  const pRes = P_Password(inp2.value);
  tip2.innerText = pRes.message;
  tip2.className = pRes.valid ? 'tip success' : 'tip error';
  inp2.className = pRes.valid ? 'success-border' : 'error-border';

  const cRes = P_Password2(inp3.value);
  tip3.innerText = cRes.message;
  tip3.className = cRes.valid ? 'tip success' : 'tip error';
  inp3.className = cRes.valid ? 'success-border' : 'error-border';

  const eRes = P_Email(inp4.value);
  tip4.innerText = eRes.message;
  tip4.className = eRes.valid ? 'tip success' : 'tip error';
  inp4.className = eRes.valid ? 'success-border' : 'error-border';

  const phRes = P_Phone(inp5.value);
  tip5.innerText = phRes.message;
  tip5.className = phRes.valid ? 'tip success' : 'tip error';
  inp5.className = phRes.valid ? 'success-border' : 'error-border';


  if (uRes.valid && pRes.valid && cRes.valid && eRes.valid && phRes.valid) {
    alert('注册成功！');
  } else {
    if (!uRes.valid) inp1.focus();
    else if (!pRes.valid) inp2.focus();
    else if (!cRes.valid) inp3.focus();
    else if (!eRes.valid) inp4.focus();
    else if (!phRes.valid) inp5.focus();
  }
});