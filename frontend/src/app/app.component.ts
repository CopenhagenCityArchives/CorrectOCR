import { Component } from '@angular/core';
import { TokenService } from './token.service'

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent {
  title = 'frontend3';

  constructor(private tokenService :TokenService){
    console.log("constructor");
  }

  public async get(){
    let token = await this.tokenService.getToken()
  }
}
