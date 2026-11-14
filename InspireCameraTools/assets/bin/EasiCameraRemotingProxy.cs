// EasiCameraRemotingProxy — 仅用于 .NET Remoting 客户端透明代理的类型定义。
//
// EasiCamera 主进程通过 IpcChannel("e3950283-80cf-4a97-a569-e6110b6e9b82")
// 在 Ipc://e3950283-80cf-4a97-a569-e6110b6e9b82/RemotingNotifyCamera 上注册了
// EasiCamera.Communication.Remoting.RemotingNotifyCamera 单例对象。
//
// .NET Remoting 的客户端需要与服务器端“同名同签名”的类型来生成透明代理，
// 因此这里用相同命名空间/类名/方法签名定义一个仅客户端的空实现
// （方法体永远不会在本进程执行，调用会被代理转发到 EasiCamera 进程）。
//
// 编译（类库）：
//   csc.exe /nologo /target:library /platform:anycpu /optimize+ /out:EasiCameraRemotingProxy.dll EasiCameraRemotingProxy.cs
using System;

namespace EasiCamera.Communication.Remoting
{
    /// <summary>与 EasiCamera.Communication.dll 中 RemotingNotifyCamera 同名同签名的客户端代理类型。</summary>
    [Serializable]
    public class RemotingNotifyCamera : MarshalByRefObject
    {
        /// <summary>Guardian 转发机身按键的入口；message 取 HidMessage 名称，如 "Key5"（拍照）。</summary>
        public bool Notify(int pid, int vid, string message)
        {
            throw new NotSupportedException("client-side transparent proxy stub");
        }
    }
}
